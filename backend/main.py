# standard library: logging for console messages, os for folders, re for patterns, uuid for random ids
import logging
import os
import re
import uuid

# PyJWT reads the login token the browser sends
import jwt
# FastAPI pieces: Depends (reusable checks), File/Form/UploadFile (uploads),
# HTTPException (error replies), Request (the raw request)
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
# lets the async notification handler run slow blocking code without freezing the server
from fastapi.concurrency import run_in_threadpool
# CORS: lets the website (served from a different address) call this API from the browser
from fastapi.middleware.cors import CORSMiddleware
# to build a JSON reply by hand
from fastapi.responses import JSONResponse
# reads the 'Authorization: Bearer <token>' header and the login form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
# serves uploaded images as plain files
from fastapi.staticfiles import StaticFiles
# raised when a token is invalid or expired
from jwt.exceptions import InvalidTokenError
# Session is a database session; joinedload fetches related rows in the same query
from sqlalchemy.orm import Session, joinedload

# my own modules: password/token helpers, settings, tables, request/response shapes,
# business rules, image storage and the Pesapal wrapper
import auth
import config
import models
import pesapal_service
import schemas
import services
import storage
# SessionLocal makes sessions, engine is the connection
from database import SessionLocal, engine
# upgrades an existing database when the server starts
from migrations import run_migrations
# the error type for wrong user input
from services import ServiceError

# show INFO messages (migrations, warnings) in the console
logging.basicConfig(level=logging.INFO)
# logger for this file
log = logging.getLogger("shamba")

# create any table that doesn't exist yet (e.g. payments on an older database)
models.Base.metadata.create_all(bind=engine)
# then add missing columns and convert old text prices into numbers
run_migrations(engine)

# the application object that uvicorn runs
app = FastAPI(title="Shamba Fresh API")

# CORS: only the websites listed in CORS_ORIGINS may call this API from a browser
app.add_middleware(
    CORSMiddleware,
    # the allowed websites
    allow_origins=config.CORS_ORIGINS,
    # no cookies are used; the token travels in a header instead
    allow_credentials=False,
    # any HTTP method (GET, POST, PUT, PATCH, DELETE) from those websites
    allow_methods=["*"],
    # any header (Authorization, Content-Type)
    allow_headers=["*"],
)

# make sure the uploads folder exists
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
# serve that folder at /uploads/..., which is how the browser loads images
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")


# any ServiceError (bad input) raised anywhere becomes a clean HTTP 400 carrying its message
@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# a failed image save becomes an HTTP 502 with a friendly message; the real reason goes to the log
@app.exception_handler(storage.StorageError)
async def storage_error_handler(request: Request, exc: storage.StorageError):
    log.error("Storage error: %s", exc)
    return JSONResponse(status_code=502, content={"detail": "We could not save the image. Please try again."})


# ---------- Dependencies ----------
# gives every request its own database session and always closes it afterwards
def get_db():
    # open a session
    db = SessionLocal()
    try:
        # hand it to the endpoint
        yield db
    # runs even if the endpoint crashed
    finally:
        # release the connection
        db.close()


# reads the token from the 'Authorization: Bearer' header (it is handed out by /api/login)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


# dependency that works out WHO is calling from the token. Any endpoint needing a logged-in user lists it
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # the reply used whenever the token is missing, wrong or expired (HTTP 401)
    credentials_exception = HTTPException(
        status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"}
    )
    # decode the token; this also checks its signature and expiry
    try:
        # fails if the token was changed or has expired
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        # 'sub' holds the username (put there at login)
        username = payload.get("sub")
        # a token without a username is useless
        if username is None:
            raise credentials_exception
    # bad signature or expired
    except InvalidTokenError:
        raise credentials_exception
    # look the user up in the database
    user = db.query(models.User).filter(models.User.username == username).first()
    # the account no longer exists
    if user is None:
        raise credentials_exception
    # the endpoint receives this user object
    return user


# dependency: logged in AND a farmer
def require_farmer(current_user: models.User = Depends(get_current_user)):
    # customers get 403 (forbidden)
    if current_user.role != "farmer":
        raise HTTPException(status_code=403, detail="Only farmers can perform this action")
    return current_user


# dependency: logged in AND not a farmer (farmers can't buy)
def require_customer(current_user: models.User = Depends(get_current_user)):
    # farmers get 403
    if current_user.role == "farmer":
        raise HTTPException(status_code=403, detail="Farmers can't place orders. Log in with a customer account to buy.")
    return current_user


# simple check that the API is running
@app.get("/")
def read_root():
    return {"message": "Shamba Fresh API is running"}


# an uptime monitor can ping this
@app.get("/health")
def health():
    return {"status": "ok"}  # point an uptime monitor here


# ======================================================================
# AUTH & PROFILE
# ======================================================================
# POST /api/signup: creates an account
@app.post("/api/signup", response_model=schemas.UserResponse)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # check and tidy the username, then lowercase it so 'Joy' and 'joy' are the same person
    username = services.clean_username(user.username).lower()
    # check the email address
    email = services.clean_email(user.email)
    # password length rules
    services.check_password(user.password)

    # is the username already taken?
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username is already taken")

    # anything except 'farmer' becomes 'customer' (the signup form sends 'buyer')
    role = "farmer" if user.role == "farmer" else "customer"
    # these stay empty for customers
    phone = payment_method = payment_number = None
    # farmers must give a contact number and payout details
    if role == "farmer":
        # turn it into the standard 254... form
        phone = services.normalize_kenyan_phone(user.phone)
        # not a valid Kenyan number
        if not phone:
            raise HTTPException(status_code=400, detail="Enter a valid contact mobile number, e.g. 0712345678")
        # check the payout method
        payment_method = services.clean_payment_method(user.payment_method)
        # check the payout number fits that method
        payment_number = services.clean_payment_number(payment_method, user.payment_number)

    # build the user row. The password is hashed here; the real password is never stored
    new_user = models.User(
        username=username, email=email, hashed_password=auth.get_password_hash(user.password),
        role=role, phone=phone, payment_method=payment_method, payment_number=payment_number,
    )
    # stage the new row
    db.add(new_user)
    # write it to the database
    db.commit()
    # reload it so it has its new id
    db.refresh(new_user)
    # sent back as a UserResponse (no password hash)
    return new_user


# POST /api/login: checks username and password and hands back a token
@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # find the user (trimmed and lowercased)
    user = db.query(models.User).filter(models.User.username == form_data.username.strip().lower()).first()
    # one message for 'no such user' and 'wrong password', so nobody can probe which usernames exist
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    # what the browser keeps after logging in (token, role, name, picture)
    return {
        "access_token": auth.create_access_token(data={"sub": user.username, "role": user.role}),
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "profile_picture": user.profile_picture,
    }


# GET /api/me: who am I? Every page uses it to refresh role, name and picture
@app.get("/api/me", response_model=schemas.UserResponse)
def read_me(current_user: models.User = Depends(get_current_user)):
    return current_user


# PUT /api/me: update my profile (email, phone and, for farmers, payout details)
@app.put("/api/me", response_model=schemas.UserResponse)
def update_profile(
    user_update: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # only the fields the browser actually sent
    fields = user_update.model_dump(exclude_unset=True)

    # a non-empty email replaces the old one (an empty one is ignored)
    if fields.get("email"):
        current_user.email = services.clean_email(fields["email"])

    # phone was sent
    if "phone" in fields:
        # trim what was typed
        raw_phone = (fields["phone"] or "").strip()
        # a number was typed: validate it
        if raw_phone:
            # standard 254... form
            phone = services.normalize_kenyan_phone(raw_phone)
            # not a valid number
            if not phone:
                raise HTTPException(status_code=400, detail="Enter a valid contact mobile number, e.g. 0712345678")
            # save it on the user
            current_user.phone = phone
        # farmers must always keep a contact number
        elif current_user.role == "farmer":
            raise HTTPException(status_code=400, detail="Farmers must keep a contact mobile number")
        # customers may clear their number
        else:
            current_user.phone = None

    # payout details exist for farmers only
    if current_user.role == "farmer" and ("payment_method" in fields or "payment_number" in fields):
        # use the newly sent method, otherwise keep the current one
        method = services.clean_payment_method(fields.get("payment_method") or current_user.payment_method)
        # the number typed, trimmed
        raw_number = (fields.get("payment_number") or "").strip()
        # a number was typed: check it fits the method
        if raw_number:
            current_user.payment_number = services.clean_payment_number(method, raw_number)
        # method changed but no new number: refuse, the old number wouldn't fit
        elif method != current_user.payment_method:
            raise HTTPException(status_code=400, detail="Enter the payment number for your new payment method")
        # save the method
        current_user.payment_method = method

    # write all changes
    db.commit()
    # reload the user
    db.refresh(current_user)
    # send the updated profile back
    return current_user


# POST /api/me/avatar: upload a profile picture
@app.post("/api/me/avatar", response_model=schemas.UserResponse)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # read at most the limit + 1 byte, so an oversized file is noticed without loading all of it
    data = file.file.read(config.MAX_AVATAR_BYTES + 1)
    # over 2 MB
    if len(data) > config.MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large. The maximum size is 2 MB.")
    # check it really is a JPG, PNG or WEBP from its bytes
    ext = services.detect_image_ext(data)

    # save the file (local disk or Cloudinary)
    new_url = storage.save_image(data, ext, "avatars")
    # remember the old picture
    old_url = current_user.profile_picture
    # point the user at the new one
    current_user.profile_picture = new_url
    # write to the database
    db.commit()
    # reload the user
    db.refresh(current_user)
    # delete the old file only after the database was updated, so a failure never leaves the user without a picture
    storage.delete_image(old_url)
    # send the updated profile back
    return current_user


# DELETE /api/me/avatar: remove my picture
@app.delete("/api/me/avatar", response_model=schemas.UserResponse)
def delete_avatar(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # remember which file to delete
    old_url = current_user.profile_picture
    # clear the link
    current_user.profile_picture = None
    # write to the database
    db.commit()
    # reload the user
    db.refresh(current_user)
    # then delete the file itself
    storage.delete_image(old_url)
    # send the updated profile back
    return current_user


# ======================================================================
# PRODUCTS
# ======================================================================
# GET /api/products: public list for the marketplace page, newest first
@app.get("/api/products", response_model=list[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    # joinedload loads each product's farmer in the same query, so showing 'By <name>' is cheap
    return (db.query(models.Product).options(joinedload(models.Product.owner))
            .order_by(models.Product.id.desc()).all())


# GET one product. The checkout page uses this to get the current price and stock
@app.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    # find the product by id
    product = (db.query(models.Product).options(joinedload(models.Product.owner))
               .filter(models.Product.id == product_id).first())
    # 404: no such product
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # sent back as a ProductResponse
    return product


# GET /api/my-products: the logged-in farmer's own products (require_farmer blocks everyone else)
@app.get("/api/my-products", response_model=list[schemas.ProductResponse])
def get_my_products(current_user: models.User = Depends(require_farmer), db: Session = Depends(get_db)):
    # only products owned by this farmer
    return (db.query(models.Product).options(joinedload(models.Product.owner))
            .filter(models.Product.farmer_id == current_user.id)
            .order_by(models.Product.id.desc()).all())


# POST /api/upload: a farmer lists a new product (a form with a photo)
@app.post("/api/upload", response_model=schemas.ProductResponse)
def upload_product(
    # these arrive as text and are checked below
    item_name: str = Form(...),
    unit_price: str = Form(...),
    unit: str = Form(...),
    stock: str = Form(...),
    # the photo
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_farmer),
):
    # tidy the product name
    name = item_name.strip()
    # must be 2 to 80 characters
    if not 2 <= len(name) <= 80:
        raise HTTPException(status_code=400, detail="Product name must be 2 to 80 characters")
    # an exact, validated price
    price = services.parse_price(unit_price)
    # a unit from the allowed list
    unit_clean = services.clean_unit(unit)
    # a whole number of at least 1
    stock_n = services.clean_stock(stock)

    # read the photo (limit 5 MB)
    data = file.file.read(config.MAX_PRODUCT_IMAGE_BYTES + 1)
    # too big
    if len(data) > config.MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large. The maximum size is 5 MB.")
    # is it really an image?
    ext = services.detect_image_ext(data)
    # save the photo first...
    image_url = storage.save_image(data, ext, "products")

    # build the product row with this farmer as the owner
    product = models.Product(item_name=name, unit_price=price, unit=unit_clean, stock=stock_n,
                             image_url=image_url, farmer_id=current_user.id)
    # ...then save to the database; if that fails the saved photo is removed so no unused file is left behind
    try:
        # stage the row
        db.add(product)
        # write it
        db.commit()
    # something went wrong while saving
    except Exception:
        # undo the half-done change
        db.rollback()
        # remove the photo that was just saved
        storage.delete_image(image_url)
        # pass the original error on
        raise
    # reload so it has its id
    db.refresh(product)
    # sent back as a ProductResponse
    return product


# PATCH /api/products/<id>: a farmer updates the stock of their product
@app.patch("/api/products/{product_id}", response_model=schemas.ProductResponse)
def update_product_stock(product_id: int, stock: str = Form(...), db: Session = Depends(get_db),
                         current_user: models.User = Depends(require_farmer)):
    # find it
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    # 404
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # 403: it belongs to another farmer
    if product.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own products")
    
    # validate and save the new stock
    product.stock = services.clean_stock(stock)
    db.commit()
    db.refresh(product)
    return product


# DELETE /api/products/<id>: a farmer removes one of their products
@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(require_farmer)):
    # find it
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    # 404
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # 403: it belongs to another farmer
    if product.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own products")

    # remember the photo so it can be deleted afterwards
    image_url = product.image_url
    # Orders keep their own copy of name/price, so history survives the delete.
    # old orders keep their own copy of name and price, so they only lose the link to the product
    db.query(models.Order).filter(models.Order.product_id == product_id).update({"product_id": None})
    # remove the product
    db.delete(product)
    # write it
    db.commit()
    # remove the photo file last
    storage.delete_image(image_url)
    # simple confirmation
    return {"detail": "Product removed"}


# ======================================================================
# CHECKOUT & PAYMENTS
# ======================================================================
# Pesapal tracking ids are letters, digits and dashes. Anything else is refused before it goes anywhere
TRACKING_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


# loads an order and checks it belongs to the logged-in customer (otherwise 404, so nobody can tell whether it exists)
def _own_order(db, order_id, user):
    # load it together with its payments
    order = (db.query(models.Order).options(joinedload(models.Order.payments))
             .filter(models.Order.id == order_id).first())
    # not found, or somebody else's
    if not order or order.buyer_username != user.username:
        raise HTTPException(status_code=404, detail="Order not found")
    # hand it back
    return order


# creates a payment attempt and returns the Pesapal page address to send the customer to
def _start_payment(db, order, user, email=None):
    """Create a payment attempt and return the Pesapal page to send the customer to."""
    # one timestamp for the new record
    now = services.now_iso()
    # record the attempt BEFORE calling Pesapal, with a unique reference (SHAMBA-<order>-<random>)
    payment = models.Payment(
        order_id=order.id,
        merchant_reference=f"SHAMBA-{order.id}-{uuid.uuid4().hex[:8]}",
        amount=order.amount, currency=order.currency or "KES",
        status="pending", created_at=now, updated_at=now,
    )
    # stage it
    db.add(payment)
    # write it
    db.commit()
    # reload it
    db.refresh(payment)

    # ask Pesapal to create the order
    try:
        # everything Pesapal needs; the amount comes from the order I stored, never from the browser
        result = pesapal_service.start_checkout(
            merchant_reference=payment.merchant_reference,
            amount=order.amount,
            description=f"{order.qty} x {order.product_name}",
            # where Pesapal sends the customer after paying
            callback_url=f"{config.FRONTEND_URL}/payment-return.html",
            # the account's email, else the one typed at checkout, else the fallback
            email=user.email or email or config.PESAPAL_FALLBACK_EMAIL,
            phone=order.phone,
            # the username stands in for a first name
            first_name=user.username,
            address=order.location or "Kenya",
        )
    # Pesapal refused or couldn't be reached
    except pesapal_service.PaymentGatewayError:
        # full details go to the log
        log.exception("Could not start payment for order %s", order.id)
        # mark this attempt failed; the order stays pending so the customer can retry from My Orders
        payment.status = "failed"
        # write it
        db.commit()
        # a friendly message; the technical reason is only in the log
        raise HTTPException(
            status_code=502,
            detail="We couldn't start the payment. Your order is saved: try again from My Orders.",
        )

    # store Pesapal's tracking id so later notifications can be matched to this payment
    payment.tracking_id = result["tracking_id"]
    # write it
    db.commit()
    # the Pesapal page to send the customer to
    return result["redirect_url"]


# asks Pesapal what happened to one payment and updates it
def _verify_payment(db, payment):
    """Ask Pesapal what happened to one payment and update it."""
    # nothing to ask about, or it can never change again
    if not payment.tracking_id or payment.status in services.SETTLED_STATES:
        return
    # ask Pesapal directly
    status_data = pesapal_service.fetch_status(payment.tracking_id)
    # apply the answer: mark the order paid, reduce stock, and so on
    services.settle_payment(db, payment, status_data)


# builds the reply used by both verify endpoints
def _verify_response(db, order, payment):
    # reload so the newest status is shown
    db.refresh(order)
    # the order plus the latest payment status
    return schemas.VerifyResponse(
        order=schemas.OrderResponse.model_validate(order),
        payment_status=payment.status if payment else order.payment_status,
    )


# POST /api/checkout: the customer presses 'Continue to payment'.
# Creates the order and returns the Pesapal page address
@app.post("/api/checkout", response_model=schemas.CheckoutResponse)
def checkout(req: schemas.CheckoutRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(require_customer)):
    # find the product being bought
    product = db.query(models.Product).filter(models.Product.id == req.product_id).first()
    # 404
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # the price comes from MY database, never from the browser
    unit_price = product.unit_price
    # a product without a valid price can't be bought
    if unit_price is None or float(unit_price) <= 0:
        raise HTTPException(status_code=400, detail="This product has no valid price yet. Please contact the farmer.")
    # is there enough in stock?
    services.check_stock(req.quantity, product.stock)

    # check the phone number
    phone = services.normalize_kenyan_phone(req.phone)
    # not a valid number
    if not phone:
        raise HTTPException(status_code=400, detail="Enter a valid phone number, e.g. 0712 345 678")
    # delivery location
    location = req.location.strip()
    # too short to be a place
    if len(location) < 3:
        raise HTTPException(status_code=400, detail="Enter your delivery location")

    # optional email typed at checkout
    email = services.clean_email(req.email) if req.email else None
    # save it on the account if the account had none
    if email and not current_user.email:
        current_user.email = email

    # build the order. Name, unit price and unit are copied so history never changes;
    # the total (amount) is worked out here on the server
    order = models.Order(
        product_name=product.item_name, unit_price=unit_price, unit=product.unit, qty=req.quantity,
        amount=services.compute_amount(unit_price, req.quantity), currency="KES",
        product_id=product.id, farmer_id=product.farmer_id, buyer_username=current_user.username,
        phone=phone, location=location, status="pending", created_at=services.now_iso(),
    )
    # stage it
    db.add(order)
    # write it
    db.commit()
    # reload it so it has its id
    db.refresh(order)

    # start the payment, then return the order number and the Pesapal page address
    return {"order_id": order.id, "redirect_url": _start_payment(db, order, current_user, email)}


# POST /api/orders/<id>/pay: 'Pay now' on an unpaid order (a retry)
@app.post("/api/orders/{order_id}/pay", response_model=schemas.CheckoutResponse)
def pay_for_order(order_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(require_customer)):
    """Start (or restart) payment for an order that is still unpaid."""
    # must be this customer's order
    order = _own_order(db, order_id, current_user)
    # already paid
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="This order has already been paid")
    # an old order with no readable amount can't be paid
    if order.amount is None or float(order.amount) <= 0:
        raise HTTPException(status_code=400, detail="This order has no valid amount. Please place a new order.")
    # the product has been deleted
    if order.product is None:
        raise HTTPException(status_code=400, detail="This product is no longer available")
    # is there still enough stock?
    services.check_stock(order.qty, order.product.stock)
    # new payment attempt, same reply as checkout
    return {"order_id": order.id, "redirect_url": _start_payment(db, order, current_user)}


# POST /api/payments/verify: the page Pesapal sends the customer back to calls this with the tracking id from the address bar
@app.post("/api/payments/verify", response_model=schemas.VerifyResponse)
def verify_by_tracking_id(req: schemas.VerifyRequest, db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """Called by the page Pesapal sends customers back to."""
    # reject odd-looking ids
    if not TRACKING_ID_RE.match(req.order_tracking_id):
        raise HTTPException(status_code=400, detail="Invalid payment reference")
    # find my payment record by tracking id
    payment = db.query(models.Payment).filter(models.Payment.tracking_id == req.order_tracking_id).first()
    # unknown, or it belongs to somebody else: both give the same 404
    if not payment or payment.order is None or payment.order.buyer_username != current_user.username:
        raise HTTPException(status_code=404, detail="Payment not found")
    # ask Pesapal and apply the answer
    try:
        # does the checking
        _verify_payment(db, payment)
    # couldn't reach Pesapal
    except pesapal_service.PaymentGatewayError:
        # details go to the log
        log.exception("Verify failed for %s", payment.merchant_reference)
        # tell the page to try again shortly
        raise HTTPException(status_code=502, detail="We couldn't check the payment just now. Please try again shortly.")
    # order plus payment status
    return _verify_response(db, payment.order, payment)


# POST /api/orders/<id>/verify: the 'Check payment' button, and the automatic re-check when the dashboard opens
@app.post("/api/orders/{order_id}/verify", response_model=schemas.VerifyResponse)
def verify_order(order_id: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """The 'Check payment' button: re-checks the latest attempts for an order."""
    # must be this customer's order
    order = _own_order(db, order_id, current_user)
    # re-check the newest attempts
    try:
        # the last 3 attempts are enough
        for payment in order.payments[-3:]:
            # ask Pesapal about each
            _verify_payment(db, payment)
    # couldn't reach Pesapal
    except pesapal_service.PaymentGatewayError:
        # details go to the log
        log.exception("Verify failed for order %s", order.id)
        # tell the page to try again shortly
        raise HTTPException(status_code=502, detail="We couldn't check the payment just now. Please try again shortly.")
    # the order with its updated status
    return _verify_response(db, order, None)


# handles one Pesapal notification. Returns False only when Pesapal itself couldn't be reached (so it can try again later)
def process_ipn(tracking_id: str) -> bool:
    """Returns False only when Pesapal itself couldn't be reached (so it can retry)."""
    # its own session, because this runs outside a normal request
    db = SessionLocal()
    # do the work, always close the session in 'finally'
    try:
        # match the notification to my payment by tracking id
        payment = db.query(models.Payment).filter(models.Payment.tracking_id == tracking_id).first()
        # unknown id: ignore it but still acknowledge
        if payment is None:
            log.warning("IPN for unknown tracking id %s", tracking_id)
            return True
        # We never trust the notification itself: we ask Pesapal directly.
        # I don't believe the notification itself: I ask Pesapal directly and use that answer
        services.settle_payment(db, payment, pesapal_service.fetch_status(tracking_id))
        # handled
        return True
    # couldn't reach Pesapal to verify
    except pesapal_service.PaymentGatewayError:
        # details go to the log
        log.exception("IPN verification failed for %s", tracking_id)
        # tells the caller to answer with an error so Pesapal retries
        return False
    # always runs
    finally:
        # close the session
        db.close()


# Pesapal's notification address. Accepts GET and POST so it works however Pesapal sends it
@app.api_route("/api/pesapal/ipn", methods=["GET", "POST"])
async def pesapal_ipn(request: Request):
    # values can arrive in the address (?OrderTrackingId=...)...
    data = dict(request.query_params)
    # ...or in a JSON body
    if request.method == "POST":
        # read the body
        try:
            # parse the JSON
            body = await request.json()
            # only a JSON object is useful
            if isinstance(body, dict):
                # merge it with the address values
                data.update(body)
        # no JSON body: that's fine
        except Exception:
            # carry on with what the address gave
            pass
    # the two values Pesapal sends: its tracking id and my own reference
    tracking_id = str(data.get("OrderTrackingId") or "")
    # my reference (only echoed back, never used to decide anything)
    merchant_ref = str(data.get("OrderMerchantReference") or "")

    # the acknowledgement Pesapal expects back
    ack = {
        "orderNotificationType": data.get("OrderNotificationType", "IPNCHANGE"),
        "orderTrackingId": tracking_id,
        "orderMerchantReference": merchant_ref,
        "status": 200,
    }
    # missing or odd id: acknowledge and do nothing
    if not TRACKING_ID_RE.match(tracking_id):
        return ack
    # verify in a worker thread so the server stays responsive
    ok = await run_in_threadpool(process_ipn, tracking_id)
    # couldn't verify: answer with an error so Pesapal can retry
    if not ok:
        # error reply
        return JSONResponse(status_code=503, content={**ack, "status": 500})
    # all fine: acknowledge
    return ack


# ======================================================================
# ORDERS
# ======================================================================
# GET /api/my-orders: the farmer's orders, paid ones only
@app.get("/api/my-orders", response_model=list[schemas.OrderResponse])
def get_my_orders(current_user: models.User = Depends(require_farmer), db: Session = Depends(get_db)):
    """Farmers only see orders that have been paid for."""
    # load with payments so payment_status is cheap
    return (db.query(models.Order).options(joinedload(models.Order.payments))
            # only this farmer's orders, and none that are still unpaid
            .filter(models.Order.farmer_id == current_user.id, models.Order.status != "pending")
            .order_by(models.Order.id.desc()).all())


# GET /api/my-orders/buying: the customer's own orders (My Orders page)
@app.get("/api/my-orders/buying", response_model=list[schemas.OrderResponse])
def get_my_orders_as_buyer(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # load with payments
    return (db.query(models.Order).options(joinedload(models.Order.payments))
            # only the caller's orders
            .filter(models.Order.buyer_username == current_user.username)
            .order_by(models.Order.id.desc()).all())


# PATCH an order's status. A farmer can only mark a paid order 'delivered'; 'paid' is set by Pesapal's confirmation, never by hand
@app.patch("/api/orders/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(order_id: int, new_status: str = Form(...), db: Session = Depends(get_db),
                        current_user: models.User = Depends(require_farmer)):
    """Farmers can only mark a paid order as delivered. 'Paid' is set by Pesapal, never by hand."""
    # nothing else is allowed
    if new_status != "delivered":
        raise HTTPException(status_code=400, detail="You can only mark an order as delivered")
    # find the order
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    # missing or another farmer's: 404
    if not order or order.farmer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    # only a paid order can be delivered
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="Only paid orders can be marked as delivered")
    # update the status
    order.status = "delivered"
    # write it
    db.commit()
    # reload it
    db.refresh(order)
    # send the updated order back
    return order


# ======================================================================
# CONTACT
# ======================================================================
# POST /api/contact: stores a message from the contact form
@app.post("/api/contact", response_model=schemas.ContactMessageResponse)
def submit_contact_form(msg: schemas.ContactMessageCreate, db: Session = Depends(get_db)):
    # tidy the text and check the email before saving
    new_msg = models.ContactMessage(
        name=msg.name.strip(), email=services.clean_email(msg.email), message=msg.message.strip(),
    )
    # stage it
    db.add(new_msg)
    # write it
    db.commit()
    # reload it so it has its id
    db.refresh(new_msg)
    # send it back
    return new_msg