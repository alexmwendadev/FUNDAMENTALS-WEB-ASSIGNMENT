# standard library: logging for console messages, os for folders, re for patterns, uuid for random ids
import logging
import os
import re
import uuid
import secrets
from datetime import datetime, timedelta, timezone

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
import email_service # For password reset emails
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
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
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
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# reads the token from the 'Authorization: Bearer' header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


# dependency that works out WHO is calling from the token
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


# dependency: logged in AND a farmer
def require_farmer(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "farmer":
        raise HTTPException(status_code=403, detail="Only farmers can perform this action")
    return current_user


# dependency: logged in AND not a farmer (farmers can't buy)
def require_customer(current_user: models.User = Depends(get_current_user)):
    if current_user.role == "farmer":
        raise HTTPException(status_code=403, detail="Farmers can't place orders. Log in with a customer account to buy.")
    return current_user


# simple check that the API is running
@app.get("/")
def read_root():
    return {"message": "Shamba Fresh API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ======================================================================
# AUTH & PROFILE
# ======================================================================
@app.post("/api/signup", response_model=schemas.UserResponse)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    username = services.clean_username(user.username).lower()
    email = services.clean_email(user.email)
    services.check_password(user.password)

    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username is already taken")

    role = "farmer" if user.role == "farmer" else "customer"
    phone = payment_method = payment_number = None
    
    if role == "farmer":
        phone = services.normalize_kenyan_phone(user.phone)
        if not phone:
            raise HTTPException(status_code=400, detail="Enter a valid contact mobile number, e.g. 0712345678")
        payment_method = services.clean_payment_method(user.payment_method)
        payment_number = services.clean_payment_number(payment_method, user.payment_number)

    new_user = models.User(
        username=username, email=email, hashed_password=auth.get_password_hash(user.password),
        role=role, phone=phone, payment_method=payment_method, payment_number=payment_number,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username.strip().lower()).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return {
        "access_token": auth.create_access_token(data={"sub": user.username, "role": user.role}),
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "profile_picture": user.profile_picture,
    }


# POST /api/forgot-password: sends an email with a reset link
@app.post("/api/forgot-password")
def forgot_password(req: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email.lower()).first()
    if not user:
        return {"message": "If that email exists, a reset link was sent."}
    
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    user.reset_token = token
    user.reset_token_expires = expires
    db.commit()

    reset_link = f"{config.FRONTEND_URL}/reset-password.html?token={token}"
    email_service.send_reset_email(user.email, reset_link)
    
    return {"message": "If that email exists, a reset link was sent."}


# POST /api/reset-password: actually resets the password using the token
@app.post("/api/reset-password")
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.reset_token == req.token).first()
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
    if user.reset_token_expires:
        expires = datetime.fromisoformat(user.reset_token_expires)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(status_code=400, detail="Reset token has expired")
            
    services.check_password(req.new_password)
    
    user.hashed_password = auth.get_password_hash(req.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return {"message": "Password updated successfully"}


@app.get("/api/me", response_model=schemas.UserResponse)
def read_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@app.put("/api/me", response_model=schemas.UserResponse)
def update_profile(
    user_update: schemas.UserUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fields = user_update.model_dump(exclude_unset=True)

    if fields.get("email"):
        current_user.email = services.clean_email(fields["email"])

    if "phone" in fields:
        raw_phone = (fields["phone"] or "").strip()
        if raw_phone:
            phone = services.normalize_kenyan_phone(raw_phone)
            if not phone:
                raise HTTPException(status_code=400, detail="Enter a valid contact mobile number, e.g. 0712345678")
            current_user.phone = phone
        elif current_user.role == "farmer":
            raise HTTPException(status_code=400, detail="Farmers must keep a contact mobile number")
        else:
            current_user.phone = None

    if current_user.role == "farmer" and ("payment_method" in fields or "payment_number" in fields):
        method = services.clean_payment_method(fields.get("payment_method") or current_user.payment_method)
        raw_number = (fields.get("payment_number") or "").strip()
        if raw_number:
            current_user.payment_number = services.clean_payment_number(method, raw_number)
        elif method != current_user.payment_method:
            raise HTTPException(status_code=400, detail="Enter the payment number for your new payment method")
        current_user.payment_method = method

    db.commit()
    db.refresh(current_user)
    return current_user


@app.post("/api/me/avatar", response_model=schemas.UserResponse)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = file.file.read(config.MAX_AVATAR_BYTES + 1)
    if len(data) > config.MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large. The maximum size is 2 MB.")
    ext = services.detect_image_ext(data)

    new_url = storage.save_image(data, ext, "avatars")
    old_url = current_user.profile_picture
    current_user.profile_picture = new_url
    db.commit()
    db.refresh(current_user)
    storage.delete_image(old_url)
    return current_user


@app.delete("/api/me/avatar", response_model=schemas.UserResponse)
def delete_avatar(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    old_url = current_user.profile_picture
    current_user.profile_picture = None
    db.commit()
    db.refresh(current_user)
    storage.delete_image(old_url)
    return current_user


# ======================================================================
# PRODUCTS
# ======================================================================
@app.get("/api/products", response_model=list[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    return (db.query(models.Product).options(joinedload(models.Product.owner))
            .order_by(models.Product.id.desc()).all())


@app.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = (db.query(models.Product).options(joinedload(models.Product.owner))
               .filter(models.Product.id == product_id).first())
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.get("/api/my-products", response_model=list[schemas.ProductResponse])
def get_my_products(current_user: models.User = Depends(require_farmer), db: Session = Depends(get_db)):
    return (db.query(models.Product).options(joinedload(models.Product.owner))
            .filter(models.Product.farmer_id == current_user.id)
            .order_by(models.Product.id.desc()).all())


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
    name = item_name.strip()
    if not 2 <= len(name) <= 80:
        raise HTTPException(status_code=400, detail="Product name must be 2 to 80 characters")
    price = services.parse_price(unit_price)
    unit_clean = services.clean_unit(unit)
    stock_n = services.clean_stock(stock)

    data = file.file.read(config.MAX_PRODUCT_IMAGE_BYTES + 1)
    if len(data) > config.MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image is too large. The maximum size is 5 MB.")
    ext = services.detect_image_ext(data)
    image_url = storage.save_image(data, ext, "products")

    product = models.Product(item_name=name, unit_price=price, unit=unit_clean, stock=stock_n,
                             category=category, image_url=image_url, farmer_id=current_user.id)
    try:
        db.add(product)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_image(image_url)
        raise
    db.refresh(product)
    return product


@app.patch("/api/products/{product_id}", response_model=schemas.ProductResponse)
def update_product_stock(product_id: int, stock: str = Form(...), db: Session = Depends(get_db),
                         current_user: models.User = Depends(require_farmer)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own products")
    
    product.stock = services.clean_stock(stock, allow_zero=True)
    db.commit()
    db.refresh(product)
    return product


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(require_farmer)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.farmer_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own products")

    image_url = product.image_url
    db.query(models.Order).filter(models.Order.product_id == product_id).update({"product_id": None})
    db.delete(product)
    db.commit()
    storage.delete_image(image_url)
    return {"detail": "Product removed"}


# ======================================================================
# CHECKOUT & PAYMENTS
# ======================================================================
TRACKING_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def _own_order(db, order_id, user):
    order = (db.query(models.Order).options(joinedload(models.Order.payments))
             .filter(models.Order.id == order_id).first())
    if not order or order.buyer_username != user.username:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def _start_payment(db, order, user, email=None):
    now = services.now_iso()
    payment = models.Payment(
        order_id=order.id,
        merchant_reference=f"SHAMBA-{order.id}-{uuid.uuid4().hex[:8]}",
        amount=order.amount, currency=order.currency or "KES",
        status="pending", created_at=now, updated_at=now,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    try:
        result = pesapal_service.start_checkout(
            merchant_reference=payment.merchant_reference,
            amount=order.amount,
            description=f"{order.qty} x {order.product_name}",
            callback_url=f"{config.FRONTEND_URL}/payment-return.html",
            email=user.email or email or config.PESAPAL_FALLBACK_EMAIL,
            phone=order.phone or "0700000000", # Fallback for Pesapal billing address
            first_name=user.username,
            address=order.location or "Kenya",
        )
    except pesapal_service.PaymentGatewayError:
        log.exception("Could not start payment for order %s", order.id)
        payment.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="We couldn't start the payment. Your order is saved: try again from My Orders.",
        )

    payment.tracking_id = result["tracking_id"]
    db.commit()
    return result["redirect_url"]


def _verify_payment(db, payment):
    if not payment.tracking_id or payment.status in services.SETTLED_STATES:
        return
    status_data = pesapal_service.fetch_status(payment.tracking_id)
    services.settle_payment(db, payment, status_data)


def _verify_response(db, order, payment):
    db.refresh(order)
    return schemas.VerifyResponse(
        order=schemas.OrderResponse.model_validate(order),
        payment_status=payment.status if payment else order.payment_status,
    )


@app.post("/api/checkout", response_model=schemas.CheckoutResponse)
def checkout(req: schemas.CheckoutRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(require_customer)):
    product = db.query(models.Product).filter(models.Product.id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    unit_price = product.unit_price
    if unit_price is None or float(unit_price) <= 0:
        raise HTTPException(status_code=400, detail="This product has no valid price yet. Please contact the farmer.")
    services.check_stock(req.quantity, product.stock)

    # PHONE IS NO LONGER REQUESTED. We use the profile phone, or a placeholder.
    phone = current_user.phone or "0700000000"

    location = req.location.strip()
    if len(location) < 3:
        raise HTTPException(status_code=400, detail="Enter your delivery location")

    email = services.clean_email(req.email) if req.email else None
    if email and not current_user.email:
        current_user.email = email

    order = models.Order(
        product_name=product.item_name, unit_price=unit_price, unit=product.unit, qty=req.quantity,
        amount=services.compute_amount(unit_price, req.quantity), currency="KES",
        product_id=product.id, farmer_id=product.farmer_id, buyer_username=current_user.username,
        phone=phone, location=location, status="pending", created_at=services.now_iso(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {"order_id": order.id, "redirect_url": _start_payment(db, order, current_user, email)}


@app.post("/api/orders/{order_id}/pay", response_model=schemas.CheckoutResponse)
def pay_for_order(order_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(require_customer)):
    order = _own_order(db, order_id, current_user)
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="This order has already been paid")
    if order.amount is None or float(order.amount) <= 0:
        raise HTTPException(status_code=400, detail="This order has no valid amount. Please place a new order.")
    if order.product is None:
        raise HTTPException(status_code=400, detail="This product is no longer available")
    services.check_stock(order.qty, order.product.stock)
    return {"order_id": order.id, "redirect_url": _start_payment(db, order, current_user)}


@app.post("/api/payments/verify", response_model=schemas.VerifyResponse)
def verify_by_tracking_id(req: schemas.VerifyRequest, db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    if not TRACKING_ID_RE.match(req.order_tracking_id):
        raise HTTPException(status_code=400, detail="Invalid payment reference")
    payment = db.query(models.Payment).filter(models.Payment.tracking_id == req.order_tracking_id).first()
    if not payment or payment.order is None or payment.order.buyer_username != current_user.username:
        raise HTTPException(status_code=404, detail="Payment not found")
    try:
        _verify_payment(db, payment)
    except pesapal_service.PaymentGatewayError:
        log.exception("Verify failed for %s", payment.merchant_reference)
        raise HTTPException(status_code=502, detail="We couldn't check the payment just now. Please try again shortly.")
    return _verify_response(db, payment.order, payment)


@app.post("/api/orders/{order_id}/verify", response_model=schemas.VerifyResponse)
def verify_order(order_id: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    order = _own_order(db, order_id, current_user)
    try:
        for payment in order.payments[-3:]:
            _verify_payment(db, payment)
    except pesapal_service.PaymentGatewayError:
        log.exception("Verify failed for order %s", order.id)
        raise HTTPException(status_code=502, detail="We couldn't check the payment just now. Please try again shortly.")
    return _verify_response(db, order, None)


def process_ipn(tracking_id: str) -> bool:
    db = SessionLocal()
    try:
        payment = db.query(models.Payment).filter(models.Payment.tracking_id == tracking_id).first()
        if payment is None:
            log.warning("IPN for unknown tracking id %s", tracking_id)
            return True
        services.settle_payment(db, payment, pesapal_service.fetch_status(tracking_id))
        return True
    except pesapal_service.PaymentGatewayError:
        log.exception("IPN verification failed for %s", tracking_id)
        return False
    finally:
        db.close()


@app.api_route("/api/pesapal/ipn", methods=["GET", "POST"])
async def pesapal_ipn(request: Request):
    data = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                data.update(body)
        except Exception:
            pass
    tracking_id = str(data.get("OrderTrackingId") or "")
    merchant_ref = str(data.get("OrderMerchantReference") or "")

    ack = {
        "orderNotificationType": data.get("OrderNotificationType", "IPNCHANGE"),
        "orderTrackingId": tracking_id,
        "orderMerchantReference": merchant_ref,
        "status": 200,
    }
    if not TRACKING_ID_RE.match(tracking_id):
        return ack
    ok = await run_in_threadpool(process_ipn, tracking_id)
    if not ok:
        return JSONResponse(status_code=503, content={**ack, "status": 500})
    return ack


# ======================================================================
# ORDERS
# ======================================================================
@app.get("/api/my-orders", response_model=list[schemas.OrderResponse])
def get_my_orders(current_user: models.User = Depends(require_farmer), db: Session = Depends(get_db)):
    return (db.query(models.Order).options(joinedload(models.Order.payments))
            .filter(models.Order.farmer_id == current_user.id, models.Order.status != "pending")
            .order_by(models.Order.id.desc()).all())


@app.get("/api/my-orders/buying", response_model=list[schemas.OrderResponse])
def get_my_orders_as_buyer(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(models.Order).options(joinedload(models.Order.payments))
            .filter(models.Order.buyer_username == current_user.username)
            .order_by(models.Order.id.desc()).all())


@app.patch("/api/orders/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(order_id: int, new_status: str = Form(...), db: Session = Depends(get_db),
                        current_user: models.User = Depends(require_farmer)):
    if new_status != "delivered":
        raise HTTPException(status_code=400, detail="You can only mark an order as delivered")
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order or order.farmer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "paid":
        raise HTTPException(status_code=400, detail="Only paid orders can be marked as delivered")
    order.status = "delivered"
    db.commit()
    db.refresh(order)
    return order


# ======================================================================
# CONTACT
# ======================================================================
@app.post("/api/contact", response_model=schemas.ContactMessageResponse)
def submit_contact_form(msg: schemas.ContactMessageCreate, db: Session = Depends(get_db)):
    new_msg = models.ContactMessage(
        name=msg.name.strip(), email=services.clean_email(msg.email), message=msg.message.strip(),
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg