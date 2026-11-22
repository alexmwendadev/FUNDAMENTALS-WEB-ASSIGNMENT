"""Business rules with no web-framework or database imports, so they can be
tested on their own (see tests/test_services.py)."""
# standard library: logging for warnings, re for pattern matching (regex),
# datetime for timestamps, Decimal for exact money maths (floats drift, Decimals don't)
import logging
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# logger shared with the rest of the app
log = logging.getLogger("shamba")

# units a farmer may sell by (the dropdown on the dashboard uses the same list)
ALLOWED_UNITS = ("kg", "bag", "sack", "crate", "bunch", "piece", "dozen", "litre", "tray", "bundle")
# ways a farmer can choose to be paid
PAYMENT_METHODS = ("mpesa", "airtel money", "till")
# upper limit for one unit price, in KES
MAX_UNIT_PRICE = Decimal("1000000")
# upper limit for the stock of one product
MAX_STOCK = 1_000_000
# money is rounded to 2 decimal places
MONEY_STEP = Decimal("0.01")
SETTLED_STATES = ("reversed",)  # a payment in one of these never changes again


# raised when the user's input is wrong. main.py turns it into an HTTP 400 reply carrying this message
class ServiceError(Exception):
    """Something is wrong with what the user sent. main.py turns it into HTTP 400."""


# current UTC time as text (e.g. 2026-11-21T10:00:00+00:00), stored in created_at / paid_at
def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- Input cleaning ----------
# turns 0712 345 678, +254712345678 etc. into 254712345678. Returns None if it isn't a valid Kenyan number
def normalize_kenyan_phone(raw):
    # strip spaces, dashes and brackets
    cleaned = re.sub(r"[\s\-()]", "", raw or "")
    # optional +254 / 254 / 0 prefix, then 9 digits that start with 7 or 1
    match = re.fullmatch(r"(?:\+?254|0)?([71]\d{8})", cleaned)
    # rebuild in the standard 254... form, or None when nothing matched
    return f"254{match.group(1)}" if match else None


# trims and lowercases an email and checks it looks like name@domain.tld
def clean_email(raw):
    email = (raw or "").strip().lower()
    # too long, or the wrong shape: reject it
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ServiceError("Enter a valid email address, e.g. alex@example.com")
    return email


# checks the username: 3 to 30 characters of letters, numbers, spaces, dot, dash, underscore.
# This also keeps HTML tricks like <script> out of usernames
def clean_username(raw):
    name = (raw or "").strip()
    # anything else is rejected
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.\-]{2,29}", name):
        raise ServiceError("Username must be 3 to 30 characters: letters, numbers, spaces, dots, dashes or underscores")
    return name


# password rules: industry standard (length, uppercase, lowercase, number, special character)
def check_password(password):
    # too short
    if len(password or "") < 8:
        raise ServiceError("Password must be at least 8 characters")
    # too long
    if len(password) > 128:
        raise ServiceError("Password is too long")
    # must have an uppercase letter
    if not re.search(r"[A-Z]", password):
        raise ServiceError("Password must contain at least one uppercase letter")
    # must have a lowercase letter
    if not re.search(r"[a-z]", password):
        raise ServiceError("Password must contain at least one lowercase letter")
    # must have a number
    if not re.search(r"\d", password):
        raise ServiceError("Password must contain at least one number")
    # must have a special character
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ServiceError("Password must contain at least one special character")


# checks the chosen payout method is one of the allowed ones
def clean_payment_method(raw):
    # tidy the text: trim spaces, lowercase
    method = (raw or "").strip().lower()
    # not allowed: reject
    if method not in PAYMENT_METHODS:
        raise ServiceError("Choose M-Pesa, Airtel Money or Till as your payment method")
    return method


# validates the payout number for the chosen method and returns it cleaned
def clean_payment_number(method, raw):
    # M-Pesa and Airtel numbers must be valid Kenyan phone numbers
    if method in ("mpesa", "airtel money"):
        number = normalize_kenyan_phone(raw)
        if not number:
            raise ServiceError("Enter a valid mobile money number, e.g. 0712345678")
        return number
    # otherwise it is a Till number: remove spaces...
    number = re.sub(r"\s", "", raw or "")
    # ...and it must be 5 to 7 digits
    if not re.fullmatch(r"\d{5,7}", number):
        raise ServiceError("A Till number has 5 to 7 digits")
    return number


# reads the price a farmer typed ('90', '1,200', '12.50') into an exact Decimal.
# Rejects zero, negatives and junk
def parse_price(raw):
    """'90', '1,200' or '12.50' -> Decimal. Rejects zero, negatives and junk."""
    # remove commas used as thousands separators
    text = (raw or "").strip().replace(",", "")
    # only digits with an optional .xx part are accepted
    if not re.fullmatch(r"\d{1,7}(\.\d{1,2})?", text):
        raise ServiceError("Enter the price as a number, e.g. 90 or 12.50")
    # safe to convert now that the text is known to be a plain number
    price = Decimal(text)
    # free or negative prices and absurdly high ones are rejected
    if price <= 0 or price > MAX_UNIT_PRICE:
        raise ServiceError("Price must be more than 0 and less than 1,000,000")
    # always return exactly 2 decimals, e.g. 90.00
    return price.quantize(MONEY_STEP)


# checks the unit (kg, bag...) is on the allowed list
def clean_unit(raw):
    # trim spaces and lowercase
    unit = (raw or "").strip().lower()
    # not on the list: reject
    if unit not in ALLOWED_UNITS:
        raise ServiceError("Choose a unit: " + ", ".join(ALLOWED_UNITS))
    return unit


# reads the quantity a farmer has available: a whole number of at least 1
def clean_stock(raw):
    # make sure it is text, then drop commas
    text = str(raw if raw is not None else "").strip().replace(",", "")
    # digits only, and between 1 and MAX_STOCK
    if not re.fullmatch(r"\d{1,7}", text) or not (1 <= int(text) <= MAX_STOCK):
        raise ServiceError("Quantity must be a whole number of at least 1")
    # hand back a real integer
    return int(text)


# ---------- Money ----------
# the order total: unit price x quantity, rounded to 2 decimals. Always calculated here on the server, never taken from the browser
def compute_amount(unit_price, qty):
    """Order total. Always calculated here, never taken from the browser."""
    # str() first so a float price can't bring in tiny rounding errors
    return (Decimal(str(unit_price)) * int(qty)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


# stops an order for more than what is available
def check_stock(qty, stock):
    # missing stock counts as 0
    stock = int(stock or 0)
    # nothing left
    if stock <= 0:
        raise ServiceError("Sorry, this product is out of stock")
    # asking for more than what is left
    if qty > stock:
        raise ServiceError(f"Only {stock} left in stock. Choose a smaller quantity")


# ---------- Images ----------
# decides the file type from the file's own first bytes (its 'magic number'), not from its name, because a name can be faked
def detect_image_ext(data):
    """Decide the file type from the file's own bytes, not from its name."""
    # JPEG files start with FF D8 FF
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    # PNG files start with an 8 byte signature
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    # WEBP files are RIFF containers with WEBP at byte 8
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    # none of the three matched: not a supported image
    raise ServiceError("That file is not a valid JPG, PNG or WEBP image")


# ---------- Old data (only used by the migration) ----------
# spellings found in old text prices, mapped to the standard unit name
_UNIT_WORDS = {"liter": "litre", "liters": "litre", "litres": "litre"}


# ONLY for the one-time migration: reads old text prices such as '90(per kg)' into (price, unit)
def parse_legacy_price(text):
    """'90(per kg)' -> (Decimal('90.00'), 'kg'). Unreadable prices give (None, unit)."""
    # drop commas so '1,200' reads as 1200
    text = (text or "").replace(",", "")
    # default unit when the text doesn't mention one
    unit = "kg"
    # look for a known unit word such as kg or bag
    word = re.search(r"\b(" + "|".join(ALLOWED_UNITS + tuple(_UNIT_WORDS)) + r")s?\b", text.lower())
    # found one: use it (liter/liters become litre)
    if word:
        unit = _UNIT_WORDS.get(word.group(1), word.group(1))
    # take the first number in the text as the price
    number = re.search(r"\d+(?:\.\d+)?", text)
    # no number at all: the price is unreadable
    if not number:
        return None, unit
    try:
        # convert to a 2 decimal Decimal
        return Decimal(number.group(0)).quantize(MONEY_STEP), unit
    # the number could not be converted: treat as unreadable
    except InvalidOperation:
        return None, unit


# ONLY for the migration: pulls the first whole number out of old text like '100kg'
def parse_legacy_quantity(text):
    # first run of digits
    number = re.search(r"\d+", (text or "").replace(",", ""))
    # no digits means None
    return int(number.group(0)) if number else None


# ---------- Payment verification ----------
# decides what Pesapal's answer means. Returns one of:
# 'completed', 'failed', 'reversed', 'pending', or 'review' (paid, but something doesn't match my records)
def evaluate_status(payment, status):
    """Decide what Pesapal's answer means. Returns one of:
    'completed', 'failed', 'reversed', 'pending', 'review' (money-in that doesn't match our records)."""
    # Pesapal's wording, e.g. 'Completed', lowercased for comparing
    desc = str(status.get("payment_status_description") or "").strip().lower()
    # Pesapal also sends a numeric code (1 completed, 2 failed, 3 reversed)
    try:
        # read it as a number
        code = int(status.get("status_code"))
    # missing or not a number: ignore the code
    except (TypeError, ValueError):
        code = None

    # money received. The code is only used when the wording is missing
    if desc == "completed" or (not desc and code == 1):
        outcome = "completed"
    # the payment attempt failed
    elif desc == "failed" or (not desc and code == 2):
        return "failed"
    # the payment was refunded or reversed afterwards
    elif desc == "reversed" or (not desc and code == 3):
        return "reversed"
    # anything else, including 'invalid', means the customer simply hasn't paid yet
    else:
        return "pending"  # includes "invalid": the customer simply hasn't paid yet

    # from here on it is a 'completed' answer, so I double-check it before trusting it. First: the reference must be mine
    ref = status.get("merchant_reference")
    # a different reference means this answer is for another payment: send to review
    if ref and str(ref) != payment.merchant_reference:
        return "review"
    # second check: the currency
    currency = status.get("currency")
    # must be the currency I asked for
    if currency and str(currency).upper() != (payment.currency or "KES").upper():
        return "review"
    # third check: the amount paid
    amount = status.get("amount")
    # only check when Pesapal sent an amount
    if amount not in (None, ""):
        try:
            # read it as an exact Decimal
            paid = Decimal(str(amount))
        except InvalidOperation:
            return "review"
        # less than the order total: never accept an underpayment. More than the total is fine
        if paid < Decimal(str(payment.amount)):
            return "review"
    # all checks passed: it really is completed
    return outcome


# applies a verified Pesapal answer to a payment and its order.
# Safe to run many times: the notification, the return page and the dashboard can all trigger it
def settle_payment(db, payment, status):
    """Apply a verified Pesapal status to a payment and its order. Safe to call
    repeatedly (IPN, return page and dashboard can all trigger it)."""
    # work out what Pesapal's answer means
    outcome = evaluate_status(payment, status)

    # a reversed payment never changes again
    if payment.status in SETTLED_STATES:
        return payment.status
    # already completed and nothing new to apply: stop. This is what stops stock being reduced twice
    if payment.status == "completed" and outcome != "reversed":
        return payment.status

    # one timestamp reused for every field I update below
    now = now_iso()
    # the order this payment belongs to
    order = payment.order
    # record when this payment last changed
    payment.updated_at = now
    # keep how they paid (M-Pesa, card...) if Pesapal told me
    payment.payment_method = status.get("payment_method") or payment.payment_method
    # keep Pesapal's confirmation code if there is one
    payment.confirmation_code = status.get("confirmation_code") or payment.confirmation_code

    # money received
    if outcome == "completed":
        # mark this payment attempt as completed
        payment.status = "completed"
        # first confirmed payment for an order that was still waiting
        if order is not None and order.status == "pending":
            # the order becomes paid (this is the only place that ever happens)
            order.status = "paid"
            # remember when it was paid
            order.paid_at = now
            # the product that was bought (empty if it has since been deleted)
            product = order.product
            # only when the product still exists
            if product is not None:
                # take the bought quantity off the stock but never below zero
                product.stock = max(0, int(product.stock or 0) - int(order.qty or 0))
        # the order was already paid or delivered, so this looks like a second payment
        elif order is not None:
            # write it to the log so I can refund it by hand
            log.warning("Payment %s completed but order %s is already %s: check for a double payment",
                        payment.merchant_reference, order.id, order.status)
    # the payment was reversed
    elif outcome == "reversed":
        # mark the payment reversed (final)
        payment.status = "reversed"
        # a paid order that hasn't been delivered becomes refunded
        if order is not None and order.status == "paid":
            # show it as refunded
            order.status = "refunded"
    # failed attempts and mismatches are only recorded on the payment
    elif outcome in ("failed", "review"):
        # the order stays pending, so the customer can try again
        payment.status = outcome
        # a mismatch needs a human to look at it
        if outcome == "review":
            # loud log entry with Pesapal's full answer
            log.error("Payment %s needs manual review: Pesapal said %s", payment.merchant_reference, status)

    # save all the changes above in one go
    db.commit()
    # tell the caller where the payment ended up
    return payment.status