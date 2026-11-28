# standard library tools: logging = console messages, os = folders, re = text patterns, uuid = unique ids, secrets = safe random tokens, datetime = dates and times
import logging
import os
import re
import uuid
import secrets
from datetime import datetime, timedelta, timezone
# PyJWT: reads and checks the signed login tokens
import jwt
# FastAPI pieces: Depends = reuse a helper in a route, File/Form/UploadFile = read uploads and form fields, HTTPException = send back an error, Request = the raw incoming request
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
# runs slow normal functions in a worker thread so they don't freeze the async server
from fastapi.concurrency import run_in_threadpool
# CORS: lets my frontend (a different address) call this API from the browser
from fastapi.middleware.cors import CORSMiddleware
# lets me send a custom JSON reply with my own status code
from fastapi.responses import JSONResponse
# the login-form format and the 'Bearer token' reader
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
# serves the uploaded image files as normal web links
from fastapi.staticfiles import StaticFiles
# the error PyJWT raises when a token is bad or expired
from jwt.exceptions import InvalidTokenError
# func lets me use SQL functions (like lower()) inside a query
from sqlalchemy import func
# Session = one conversation with the database; joinedload = fetch related rows in the same query (faster)
from sqlalchemy.orm import Session, joinedload

# my own files: auth = passwords and tokens, config = settings, models = database tables, pesapal_service = payments,
# schemas = shapes of requests and replies, services = business rules, storage = saving images, email_service = sends emails
import auth
import config
import models
import pesapal_service
import schemas
import services
import storage
import email_service
# SessionLocal makes database sessions; engine is the connection itself
from database import SessionLocal, engine
# from migrations import run_migrations
# the error I raise when a rule is broken (e.g. weak password); it becomes a 400 reply below
from services import ServiceError

# show INFO messages and above in the console
logging.basicConfig(level=logging.INFO)
# my logger, named 'shamba' so my messages are easy to spot
log = logging.getLogger("shamba")

# 1. Create tables directly based on the updated models
# reads every class in models.py and creates its table if it is missing (it never changes a table that already exists)
models.Base.metadata.create_all(bind=engine)

# 2. We commented out run_migrations so it doesn't crash Neon with old schema checks
# run_migrations(engine)

# the app itself; every @app.get / @app.post below becomes a URL people can call
app = FastAPI(title="Shamba Fresh API")

# CORS rules: only the websites listed in config.CORS_ORIGINS may call this API from a browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# make sure the uploads folder exists (no error if it already does)
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
# any file in the uploads folder can be opened at /uploads/<filename>
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")

# whenever a ServiceError is raised anywhere, reply with a 400 and its message
@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

# if saving an image fails (e.g. Cloudinary is down), log it and reply with a friendly 502
@app.exception_handler(storage.StorageError)
async def storage_error_handler(request: Request, exc: storage.StorageError):
    log.error("Storage error: %s", exc)
    return JSONResponse(status_code=502, content={"detail": "We could not save the image. Please try again."})

# gives each request its own database session and ALWAYS closes it afterwards
def get_db():
    # open a new session
    db = SessionLocal()
    try:
        # hand it to the route; the code resumes here once the route has finished
        yield db
    finally:
        # close it even if the route crashed
        db.close()

# tells FastAPI to read 'Authorization: Bearer <token>' from requests; tokenUrl is the login route
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# turns the token in the request into the logged-in User row (or a 401 error). Routes use it with Depends()
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # the one error I send for any token problem
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        # check the signature and the expiry, then read what is inside the token
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        # 'sub' is the username I put into the token at login
        username = payload.get("sub")
        # a token with no username is useless
        if username is None:
            raise credentials_exception
    # tampered with, signed with the wrong key, or expired
    except InvalidTokenError:
        raise credentials_exception
    # look the user up: they may have been deleted since the token was made
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# same as get_current_user but only lets farmers through
def require_farmer(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "farmer":
        raise HTTPException(status_code=403, detail="Only farmers can perform this action")
    return current_user

# only lets non-farmers through (farmers sell, they can't buy)
def require_customer(current_user: models.User = Depends(get_current_user)):
    if current_user.role == "farmer":
        raise HTTPException(status_code=403, detail="Farmers can't place orders. Log in with a customer account to buy.")
    return current_user

# simple check that the API is alive
@app.get("/")
def read_root():
    return {"message": "Shamba Fresh API is running"}

# the hosting service calls this to see if the app is up
@app.get("/health")
def health():
    return {"status": "ok"}

# creates a new account
@app.post("/api/signup", response_model=schemas.UserResponse)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # tidy and check the username; stored in lowercase so logins aren't case sensitive
    username = services.clean_username(user.username).lower()
    # check the email looks real and make it lowercase
    email = services.clean_email(user.email)
    # reject weak passwords
    services.check_password(user.password)

    # usernames must be unique
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username is already taken")

    # only 'farmer' is accepted; anything else becomes 'customer' so nobody can make themselves something else by editing the request
    role = "farmer" if user.role == "farmer" else "customer"
    # these only apply to farmers, so they start empty
    phone = payment_method = payment_number = None
    
    # farmers must give a contact number and say where they want to be paid
    if role == "farmer":
        # turns 0712... into 254712... (the format payments need)
        phone = services.normalize_kenyan_phone(user.phone)
        if not phone:
            raise HTTPException(status_code=400, detail="Enter a valid contact mobile number, e.g. 0712345678")
        payment_method = services.clean_payment_method(user.payment_method)
        payment_number = services.clean_payment_number(payment_method, user.payment_number)

    # build the user row; the password is hashed (argon2) so the real password is never stored
    new_user = models.User(
        username=username, email=email, hashed_password=auth.get_password_hash(user.password),
        role=role, phone=phone, payment_method=payment_method, payment_number=payment_number,
    )
    # stage the new row
    db.add(new_user)
    # save it to the database
    db.commit()
    # reload it so it has the id the database gave it
    db.refresh(new_user)
    # sent back as JSON (UserResponse leaves out the password hash)
    return new_user

# checks username + password and hands back a login token
@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # find the user (usernames are stored in lowercase)
    user = db.query(models.User).filter(models.User.username == form_data.username.strip().lower()).first()
    # one message for 'no such user' and 'wrong password' so nobody can discover which usernames exist
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    # the browser keeps this token and sends it with every later request
    return {
        "access_token": auth.create_access_token(data={"sub": user.username, "role": user.role}),
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "profile_picture": user.profile_picture,
    }

# step 1 of the reset: emails the user a link that carries a one-hour token
@app.post("/api/forgot-password")
def forgot_password(req: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    # the email typed on the forgot-password page, cleaned the same way signup cleans it
    email = req.email.strip().lower()
    # BUG FIX: signup never forced emails to be unique, so one email can belong to several accounts.
    # The old code used .first(), so the reset went to ONE account (often not the one being logged into)
    # and the other account kept its old password. Now we find EVERY account that uses this email.
    # func.lower() on both sides also catches old accounts saved with capital letters in the email.
    users = db.query(models.User).filter(func.lower(models.User.email) == email).all()
    # no account has that email: still answer 'sent' so nobody can find out which emails are registered
    if not users:
        return {"message": "If that email exists, a reset link was sent."}

    # a long random string that only the emailed link knows
    token = secrets.token_urlsafe(32)
    # valid for one hour from now (saved as text)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    # the same token goes on every matching account, so the one emailed link resets all of them
    for user in users:
        user.reset_token = token
        user.reset_token_expires = expires
    db.commit()

    # the page the email button opens, with the token in the address
    reset_link = f"{config.FRONTEND_URL}/reset-password.html?token={token}"
    # send the email through Brevo
    email_service.send_reset_email(users[0].email, reset_link)

    return {"message": "If that email exists, a reset link was sent."}

# step 2 of the reset: the new-password page posts the token and the new password here
@app.post("/api/reset-password")
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    # every account that was given this token (see forgot_password above)
    users = db.query(models.User).filter(models.User.reset_token == req.token).all()
    # nobody holds this token: the link is wrong or was already used
    if not users:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # enforce the one-hour limit
    if users[0].reset_token_expires:
        # the expiry was saved as text, so turn it back into a real date
        expires = datetime.fromisoformat(users[0].reset_token_expires)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(status_code=400, detail="Reset token has expired")

    # Check password strength
    services.check_password(req.new_password)

    # hash once, then save the new hash on every matching account
    new_hash = auth.get_password_hash(req.new_password)
    for user in users:
        user.hashed_password = new_hash
        # Clear the reset token so the link can't be used again
        user.reset_token = None
        user.reset_token_expires = None

    # Commit to the database safely
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"Failed to save new password for {users[0].username}: {e}")
        raise HTTPException(status_code=500, detail="Could not update password in database.")

    # Safety check: read each account back from the database and confirm the NEW password
    # really works. If it doesn't, tell the user instead of pretending it worked.
    for user in users:
        db.refresh(user)
        if not auth.verify_password(req.new_password, user.hashed_password):
            log.error(f"Password for {user.username} did not change after reset")
            raise HTTPException(status_code=500, detail="Password was not saved. Please try again.")

    return {"message": "Password updated successfully"}

# returns the profile of whoever is logged in
@app.get("/api/me", response_model=schemas.UserResponse)
def read_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# updates the logged-in user's email, phone and payment details
@app.put("/api/me", response_model=schemas.UserResponse)
def update_profile(
    user_update: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # only the fields the browser actually sent, so fields that were left out aren't wiped
    fields = user_update.model_dump(exclude_unset=True)

    # new email: check it and save it
    if fields.get("email"):
        current_user.email = services.clean_email(fields["email"])

    # phone number changes
    if "phone" in fields:
        # trim spaces; an empty string means 'remove my number'
        raw_phone = (fields["phone"] or "").strip()
        if raw_phone:
            phone = services.normalize_kenyan_phone(raw_phone)
            if not phone:
                raise HTTPException(status_code=400, detail="Enter a valid contact mobile number, e.g. 0712345678")
            current_user.phone = phone
        # farmers can't clear their number: buyers need it to reach them
        elif current_user.role == "farmer":
            raise HTTPException(status_code=400, detail="Farmers must keep a contact mobile number")
        else:
            current_user.phone = None

    # payment details only exist for farmers
    if current_user.role == "farmer" and ("payment_method" in fields or "payment_number" in fields):
        # use the new method if one was sent, otherwise keep the old one
        method = services.clean_payment_method(fields.get("payment_method") or current_user.payment_method)
        raw_number = (fields.get("payment_number") or "").strip()
        if raw_number:
            current_user.payment_number = services.clean_payment_number(method, raw_number)
        # switching method (e.g. M-Pesa to Till) needs a matching new number
        elif method != current_user.payment_method:
            raise HTTPException(status_code=400, detail="Enter the payment number for your new payment method")
        current_user.payment_method = method

    # save all the changes in one go
    db.commit()
    db.refresh(current_user)
    return current_user

# uploads a profile picture
@app.post("/api/me/avatar", response_model=schemas.UserResponse)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # read one byte more than the limit so I can tell when the file is too big
    data = file.file.read(config.MAX_AVATAR_BYTES + 1)
    if len(data) > config.MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large. The maximum size is 2 MB.")
    # check the real file type from its first bytes (not the file name): JPG, PNG or WEBP only
    ext = services.detect_image_ext(data)

    # store the image (Cloudinary or local folder) and get its link
    new_url = storage.save_image(data, ext, "avatars")
    # remember the old picture so it can be deleted
    old_url = current_user.profile_picture
    current_user.profile_picture = new_url
    db.commit()
    db.refresh(current_user)
    # delete the old picture only AFTER the new one is safely saved
    storage.delete_image(old_url)
    return current_user

# removes the profile picture
@app.delete("/api/me/avatar", response_model=schemas.UserResponse)
def delete_avatar(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    old_url = current_user.profile_picture
    current_user.profile_picture = None
    db.commit()
    db.refresh(current_user)
    storage.delete_image(old_url)
    return current_user

# the list of all products for the shop page, newest first
@app.get("/api/products", response_model=list[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    # joinedload fetches each farmer in the same query instead of one extra query per product
    return (db.query(models.Product).options(joinedload(models.Product.owner))
            .order_by(models.Product.id.desc()).all())

# one product by its id (404 if it doesn't exist)
@app.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = (db.query(models.Product).options(joinedload(models.Product.owner))
               .filter(models.Product.id == product_id).first())
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

# only the logged-in farmer's own products
@app.get("/api/my-products", response_model=list[schemas.ProductResponse])
def get_my_products(current_user: models.User = Depends(require_farmer), db: Session = Depends(get_db)):
    return (db.query(models.Product).options(joinedload(models.Product.owner))
            .filter(models.Product.farmer_id == current_user.id)
            .order_by(models.Product.id.desc()).all())

# a farmer adds a new product (form fields plus an image file)
@app.post("/api/upload", response_model=schemas.ProductResponse)
def upload_product(
    item_name: str = Form(...),
    unit_price: str = Form(...),
    unit: str = Form(...),
    stock: str = Form(...),
    category: str = Form("vegetables"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_farmer),
):
    # clean and check every field before touching the database
    name = item_name.strip()
    if not 2 <= len(name) <= 80:
        raise HTTPException(status_code=400, detail="Product name must be 2 to 80 characters")
    price = services.parse_price(unit_price)
    unit_clean = services.clean_unit(unit)
    stock_n = services.clean_stock(stock)

    # read the product photo (max 5 MB)
    data = file.file.read(config.MAX_PRODUCT_IMAGE_BYTES + 1)
    if len(data) > config.MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large. The maximum size is 5 MB.")
    ext = services.detect_image_ext(data)
    # save the image first so the product row can store its link
    image_url = storage.save_image(data, ext, "products")

    # build the product row, owned by the logged-in farmer
    product = models.Product(item_name=name, unit_price=price, unit=unit_clean, stock=stock_n,
                             category=category, image_url=image_url, farmer_id=current_user.id)
    # if the database save fails, delete the image I just stored so no orphan files are left behind
    try:
        db.add(product)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_image(image_url)
        raise
    db.refresh(product)
    return product

# a farmer updates the stock of one of their products
@app.patch("/api/products/{product_id}", response_model=schemas.ProductResponse)
def update_product_stock(product_id: int, stock: str = Form(...), db: Session = Depends(get_db),
                         current_user: models.User = Depends(require_farmer)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # farmers can only touch their own products
    if product.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own products")
    
    # 0 is allowed here (it means sold out)
    product.stock = services.clean_stock(stock, allow_zero=True)
    db.commit()
    db.refresh(product)
    return product

# a farmer removes a product
@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(require_farmer)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own products")

    # remember the image link so the file can be deleted once the row is gone
    image_url = product.image_url
    # keep old orders for the history, just detach them from the deleted product
    db.query(models.Order).filter(models.Order.product_id == product_id).update({"product_id": None})
    # remove the product row
    db.delete(product)
    db.commit()
    # remove the image file last
    storage.delete_image(image_url)
    return {"detail": "Product removed"}

# a payment tracking id is only letters, numbers and dashes (8 to 64 long); anything else is rejected
TRACKING_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")

# fetches an order but only if it belongs to this user
def _own_order(db, order_id, user):
    order = (db.query(models.Order).options(joinedload(models.Order.payments))
             .filter(models.Order.id == order_id).first())
    # not found OR not theirs: the same 404 either way so order numbers can't be probed
    if not order or order.buyer_username != user.username:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

# creates a payment record and asks Pesapal for a checkout page; returns the link to send the buyer to
def _start_payment(db, order, user, email=None):
    # current time as text, used for created/updated dates
    now = services.now_iso()
    # my own record of this attempt; merchant_reference is the unique code Pesapal will echo back to me
    payment = models.Payment(
        order_id=order.id,
        merchant_reference=f"SHAMBA-{order.id}-{uuid.uuid4().hex[:8]}",
        amount=order.amount, currency=order.currency or "KES",
        status="pending", created_at=now, updated_at=now,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    # Pesapal needs a phone: the order's first, then the user's, then a placeholder
    pesapal_phone = order.phone or user.phone or "254712345678"

    # ask Pesapal to open a checkout
    try:
        # callback_url is the page Pesapal sends the buyer back to after paying
        result = pesapal_service.start_checkout(
            merchant_reference=payment.merchant_reference,
            amount=order.amount,
            description=f"{order.qty} x {order.product_name}",
            callback_url=f"{config.FRONTEND_URL}/payment-return.html",
            email=user.email or email or config.PESAPAL_FALLBACK_EMAIL,
            phone=pesapal_phone,
            first_name=user.username,
            address=order.location or "Kenya",
        )
    # Pesapal failed: mark this attempt failed but keep the order so the buyer can retry from My Orders
    except pesapal_service.PaymentGatewayError:
        log.exception("Could not start payment for order %s", order.id)
        payment.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="We couldn't start the payment. Your order is saved: try again from My Orders.",
        )

    # Pesapal's own id for this payment; used later to check whether it was paid
    payment.tracking_id = result["tracking_id"]
    db.commit()
    # where the browser goes to actually pay
    return result["redirect_url"]

# asks Pesapal what really happened and updates the order
def _verify_payment(db, payment):
    # nothing to check yet, or the payment is already final
    if not payment.tracking_id or payment.status in services.SETTLED_STATES:
        return
    # ask Pesapal for the real status
    status_data = pesapal_service.fetch_status(payment.tracking_id)
    # update the payment, the order and the stock from that answer
    services.settle_payment(db, payment, status_data)

# packages the order and payment status in the shape the frontend expects
def _verify_response(db, order, payment):
    # reload so the order shows its newest status
    db.refresh(order)
    return schemas.VerifyResponse(
        order=schemas.OrderResponse.model_validate(order),
        payment_status=payment.status if payment else order.payment_status,
    )

# the buyer pressed Pay: create the order, then start the payment
@app.post("/api/checkout", response_model=schemas.CheckoutResponse)
def checkout(req: schemas.CheckoutRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(require_customer)):
    # find the product being bought
    product = db.query(models.Product).filter(models.Product.id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # never trust a price sent from the browser: use the one saved in the database
    unit_price = product.unit_price
    if unit_price is None or float(unit_price) <= 0:
        raise HTTPException(status_code=400, detail="This product has no valid price yet. Please contact the farmer.")
    # refuse if there isn't enough stock
    services.check_stock(req.quantity, product.stock)

    # use the buyer's saved phone number
    phone = current_user.phone 

    # the delivery place must be filled in
    location = req.location.strip()
    if len(location) < 3:
        raise HTTPException(status_code=400, detail="Enter your delivery location")

    # the buyer may give an email at checkout; save it if their account has none
    email = services.clean_email(req.email) if req.email else None
    if email and not current_user.email:
        current_user.email = email

    # the order starts as 'pending' until Pesapal confirms the payment
    order = models.Order(
        product_name=product.item_name, unit_price=unit_price, unit=product.unit, qty=req.quantity,
        amount=services.compute_amount(unit_price, req.quantity), currency="KES",
        product_id=product.id, farmer_id=product.farmer_id, buyer_username=current_user.username,
        phone=phone, location=location, status="pending", created_at=services.now_iso(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # the frontend sends the buyer to this Pesapal link
    return {"order_id": order.id, "redirect_url": _start_payment(db, order, current_user, email)}

# retry the payment on an order that is still pending
@app.post("/api/orders/{order_id}/pay", response_model=schemas.CheckoutResponse)
def pay_for_order(order_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(require_customer)):
    order = _own_order(db, order_id, current_user)
    # an order can't be paid twice
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="This order has already been paid")
    # guard against old orders that have no amount
    if order.amount is None or float(order.amount) <= 0:
        raise HTTPException(status_code=400, detail="This order has no valid amount. Please place a new order.")
    # the farmer deleted this product
    if order.product is None:
        raise HTTPException(status_code=400, detail="This product is no longer available")
    services.check_stock(order.qty, order.product.stock)
    return {"order_id": order.id, "redirect_url": _start_payment(db, order, current_user)}

# the buyer comes back from Pesapal with a tracking id: confirm the payment here
@app.post("/api/payments/verify", response_model=schemas.VerifyResponse)
def verify_by_tracking_id(req: schemas.VerifyRequest, db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    # reject odd-looking ids early
    if not TRACKING_ID_RE.match(req.order_tracking_id):
        raise HTTPException(status_code=400, detail="Invalid payment reference")
    # find my record of this payment
    payment = db.query(models.Payment).filter(models.Payment.tracking_id == req.order_tracking_id).first()
    # 404 as well when it belongs to someone else, so ids can't be guessed
    if not payment or payment.order is None or payment.order.buyer_username != current_user.username:
        raise HTTPException(status_code=404, detail="Payment not found")
    # ask Pesapal; if it is down, tell the buyer to try again (the order is not lost)
    try:
        _verify_payment(db, payment)
    except pesapal_service.PaymentGatewayError:
        log.exception("Verify failed for %s", payment.merchant_reference)
        raise HTTPException(status_code=502, detail="We couldn't check the payment just now. Please try again shortly.")
    return _verify_response(db, payment.order, payment)

# the 'check payment' button on My Orders; re-checks the last 3 attempts
@app.post("/api/orders/{order_id}/verify", response_model=schemas.VerifyResponse)
def verify_order(order_id: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    order = _own_order(db, order_id, current_user)
    try:
        # only the 3 newest attempts are re-checked
        for payment in order.payments[-3:]:
            _verify_payment(db, payment)
    except pesapal_service.PaymentGatewayError:
        log.exception("Verify failed for order %s", order.id)
        raise HTTPException(status_code=502, detail="We couldn't check the payment just now. Please try again shortly.")
    return _verify_response(db, order, None)

# handles Pesapal's server-to-server message saying 'this payment changed'. Returns True when handled
def process_ipn(tracking_id: str) -> bool:
    # this isn't a normal route, so there's no get_db: I open and close my own session
    db = SessionLocal()
    try:
        payment = db.query(models.Payment).filter(models.Payment.tracking_id == tracking_id).first()
        # unknown id: nothing to do, answer OK so Pesapal stops retrying
        if payment is None:
            log.warning("IPN for unknown tracking id %s", tracking_id)
            return True
        # ask Pesapal for the real status and update the order
        services.settle_payment(db, payment, pesapal_service.fetch_status(tracking_id))
        return True
    # return False so Pesapal tries again later
    except pesapal_service.PaymentGatewayError:
        log.exception("IPN verification failed for %s", tracking_id)
        return False
    finally:
        db.close()

# the address Pesapal calls when a payment changes (it may use GET or POST)
@app.api_route("/api/pesapal/ipn", methods=["GET", "POST"])
async def pesapal_ipn(request: Request):
    # the details can arrive in the address...
    data = dict(request.query_params)
    # ...or in a JSON body
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                data.update(body)
        except Exception:
            pass
    tracking_id = str(data.get("OrderTrackingId") or "")
    merchant_ref = str(data.get("OrderMerchantReference") or "")

    # the reply Pesapal expects back
    ack = {
        "orderNotificationType": data.get("OrderNotificationType", "IPNCHANGE"),
        "orderTrackingId": tracking_id,
        "orderMerchantReference": merchant_ref,
        "status": 200,
    }
    # junk id: acknowledge it but ignore it
    if not TRACKING_ID_RE.match(tracking_id):
        return ack
    # the database work blocks, so it runs in a worker thread
    ok = await run_in_threadpool(process_ipn, tracking_id)
    # tell Pesapal it failed so it tries again
    if not ok:
        return JSONResponse(status_code=503, content={**ack, "status": 500})
    return ack

# orders for the logged-in farmer's products (pending ones are hidden because they aren't paid yet)
@app.get("/api/my-orders", response_model=list[schemas.OrderResponse])
def get_my_orders(current_user: models.User = Depends(require_farmer), db: Session = Depends(get_db)):
    return (db.query(models.Order).options(joinedload(models.Order.payments))
            .filter(models.Order.farmer_id == current_user.id, models.Order.status != "pending")
            .order_by(models.Order.id.desc()).all())

# orders the logged-in user has placed as a buyer
@app.get("/api/my-orders/buying", response_model=list[schemas.OrderResponse])
def get_my_orders_as_buyer(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(models.Order).options(joinedload(models.Order.payments))
            .filter(models.Order.buyer_username == current_user.username)
            .order_by(models.Order.id.desc()).all())

# a farmer marks a paid order as delivered
@app.patch("/api/orders/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(order_id: int, new_status: str = Form(...), db: Session = Depends(get_db),
                        current_user: models.User = Depends(require_farmer)):
    # the only change a farmer is allowed to make
    if new_status != "delivered":
        raise HTTPException(status_code=400, detail="You can only mark an order as delivered")
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    # farmers can only update their own orders
    if not order or order.farmer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    # you can't deliver something that wasn't paid for
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="Only paid orders can be marked as delivered")
    order.status = "delivered"
    db.commit()
    db.refresh(order)
    return order

# saves a message from the contact form
@app.post("/api/contact", response_model=schemas.ContactMessageResponse)
def submit_contact_form(msg: schemas.ContactMessageCreate, db: Session = Depends(get_db)):
    new_msg = models.ContactMessage(
        name=msg.name.strip(), email=services.clean_email(msg.email), message=msg.message.strip(),
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg