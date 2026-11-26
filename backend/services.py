"""Business rules with no web-framework or database imports, so they can be
tested on their own (see tests/test_services.py)."""
import logging
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

log = logging.getLogger("shamba")

ALLOWED_UNITS = ("kg", "bag", "sack", "crate", "bunch", "piece", "dozen", "litre", "tray", "bundle")
PAYMENT_METHODS = ("mpesa", "airtel money", "till")
MAX_UNIT_PRICE = Decimal("1000000")
MAX_STOCK = 1_000_000
MONEY_STEP = Decimal("0.01")
SETTLED_STATES = ("reversed",)

class ServiceError(Exception):
    pass

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_kenyan_phone(raw):
    cleaned = re.sub(r"[\s\-()]", "", raw or "")
    match = re.fullmatch(r"(?:\+?254|0)?([71]\d{8})", cleaned)
    return f"254{match.group(1)}" if match else None

def clean_email(raw):
    email = (raw or "").strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ServiceError("Enter a valid email address, e.g. alex@example.com")
    return email

def clean_username(raw):
    name = (raw or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.\-]{2,29}", name):
        raise ServiceError("Username must be 3 to 30 characters: letters, numbers, spaces, dots, dashes or underscores")
    return name

def check_password(password):
    if len(password or "") < 8:
        raise ServiceError("Password must be at least 8 characters")
    if len(password) > 128:
        raise ServiceError("Password is too long")
    if not re.search(r"[A-Z]", password):
        raise ServiceError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ServiceError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ServiceError("Password must contain at least one number")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ServiceError("Password must contain at least one special character")

def clean_payment_method(raw):
    method = (raw or "").strip().lower()
    if method not in PAYMENT_METHODS:
        raise ServiceError("Choose M-Pesa, Airtel Money or Till as your payment method")
    return method

def clean_payment_number(method, raw):
    if method in ("mpesa", "airtel money"):
        number = normalize_kenyan_phone(raw)
        if not number:
            raise ServiceError("Enter a valid mobile money number, e.g. 0712345678")
        return number
    number = re.sub(r"\s", "", raw or "")
    if not re.fullmatch(r"\d{5,7}", number):
        raise ServiceError("A Till number has 5 to 7 digits")
    return number

def parse_price(raw):
    text = (raw or "").strip().replace(",", "")
    if not re.fullmatch(r"\d{1,7}(\.\d{1,2})?", text):
        raise ServiceError("Enter the price as a number, e.g. 90 or 12.50")
    price = Decimal(text)
    if price <= 0 or price > MAX_UNIT_PRICE:
        raise ServiceError("Price must be more than 0 and less than 1,000,000")
    return price.quantize(MONEY_STEP)

def clean_unit(raw):
    unit = (raw or "").strip().lower()
    if unit not in ALLOWED_UNITS:
        raise ServiceError("Choose a unit: " + ", ".join(ALLOWED_UNITS))
    return unit

def clean_stock(raw, allow_zero=False):
    text = str(raw if raw is not None else "").strip().replace(",", "")
    if not re.fullmatch(r"\d{1,7}", text) or not ((0 if allow_zero else 1) <= int(text) <= MAX_STOCK):
        raise ServiceError("Quantity must be a whole number" + ("" if allow_zero else " of at least 1"))
    return int(text)

def compute_amount(unit_price, qty):
    return (Decimal(str(unit_price)) * int(qty)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)

def check_stock(qty, stock):
    stock = int(stock or 0)
    if stock <= 0:
        raise ServiceError("Sorry, this product is out of stock")
    if qty > stock:
        raise ServiceError(f"Only {stock} left in stock. Choose a smaller quantity")

def detect_image_ext(data):
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ServiceError("That file is not a valid JPG, PNG or WEBP image")

_UNIT_WORDS = {"liter": "litre", "liters": "litre", "litres": "litre"}

def parse_legacy_price(text):
    text = (text or "").replace(",", "")
    unit = "kg"
    word = re.search(r"\b(" + "|".join(ALLOWED_UNITS + tuple(_UNIT_WORDS)) + r")s?\b", text.lower())
    if word:
        unit = _UNIT_WORDS.get(word.group(1), word.group(1))
    number = re.search(r"\d+(?:\.\d+)?", text)
    if not number:
        return None, unit
    try:
        return Decimal(number.group(0)).quantize(MONEY_STEP), unit
    except InvalidOperation:
        return None, unit

def parse_legacy_quantity(text):
    number = re.search(r"\d+", (text or "").replace(",", ""))
    return int(number.group(0)) if number else None

def evaluate_status(payment, status):
    desc = str(status.get("payment_status_description") or "").strip().lower()
    try:
        code = int(status.get("status_code"))
    except (TypeError, ValueError):
        code = None

    if desc == "completed" or (not desc and code == 1):
        outcome = "completed"
    elif desc == "failed" or (not desc and code == 2):
        return "failed"
    elif desc == "reversed" or (not desc and code == 3):
        return "reversed"
    else:
        return "pending"

    ref = status.get("merchant_reference")
    if ref and str(ref) != payment.merchant_reference:
        return "review"
    currency = status.get("currency")
    if currency and str(currency).upper() != (payment.currency or "KES").upper():
        return "review"
    amount = status.get("amount")
    if amount not in (None, ""):
        try:
            paid = Decimal(str(amount))
        except InvalidOperation:
            return "review"
        if paid < Decimal(str(payment.amount)):
            return "review"
    return outcome

def settle_payment(db, payment, status):
    outcome = evaluate_status(payment, status)

    if payment.status in SETTLED_STATES:
        return payment.status
    if payment.status == "completed" and outcome != "reversed":
        return payment.status

    now = now_iso()
    order = payment.order
    payment.updated_at = now
    payment.payment_method = status.get("payment_method") or payment.payment_method
    payment.confirmation_code = status.get("confirmation_code") or payment.confirmation_code

    if outcome == "completed":
        payment.status = "completed"
        if order is not None and order.status == "pending":
            order.status = "paid"
            order.paid_at = now
            
            # Grab the real phone number from Pesapal if we don't have it
            if not order.phone:
                p_phone = status.get("phone_number") or (status.get("billing_address") or {}).get("phone_number")
                if p_phone:
                    clean_p = normalize_kenyan_phone(p_phone)
                    order.phone = clean_p or p_phone

            product = order.product
            if product is not None:
                product.stock = max(0, int(product.stock or 0) - int(order.qty or 0))
        elif order is not None:
            log.warning("Payment %s completed but order %s is already %s", payment.merchant_reference, order.id, order.status)
    
    elif outcome == "reversed":
        payment.status = "reversed"
        if order is not None and order.status == "paid":
            order.status = "refunded"
    elif outcome in ("failed", "review"):
        payment.status = outcome
        if outcome == "review":
            log.error("Payment %s needs manual review: Pesapal said %s", payment.merchant_reference, status)

    db.commit()
    return payment.status