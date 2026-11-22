"""Run with:  python tests/test_services.py   (or: pytest)"""
import os
import sys
from decimal import Decimal
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import services as s  # noqa: E402


def raises(fn, *args):
    try:
        fn(*args)
    except s.ServiceError:
        return True
    return False


class FakeDB:
    commits = 0
    def commit(self): self.commits += 1


def make(order_status="pending", stock=10, qty=2, amount="180.00"):
    product = NS(stock=stock)
    order = NS(id=1, status=order_status, qty=qty, paid_at=None, product=product)
    payment = NS(order=order, merchant_reference="SHAMBA-1-ab12cd34", amount=Decimal(amount), currency="KES",
                 status="pending", payment_method=None, confirmation_code=None, updated_at=None)
    return payment, order, product


GOOD = {"payment_status_description": "Completed", "status_code": 1, "merchant_reference": "SHAMBA-1-ab12cd34",
        "amount": 180.0, "currency": "KES", "payment_method": "MpesaKE", "confirmation_code": "ABC123"}


# ---------- money ----------
def test_compute_amount():
    assert s.compute_amount(Decimal("90.00"), 3) == Decimal("270.00")
    assert s.compute_amount("12.50", 3) == Decimal("37.50")
    assert s.compute_amount(Decimal("0.10"), 3) == Decimal("0.30")      # no float drift


def test_parse_price():
    assert s.parse_price("90") == Decimal("90.00")
    assert s.parse_price("1,200") == Decimal("1200.00")                  # old bug: this became KES 1
    assert s.parse_price("12.5") == Decimal("12.50")
    for bad in ("", "0", "0.00", "-5", "abc", "90/kg", "1e5", "12.345", "99999999"):
        assert raises(s.parse_price, bad), bad


def test_stock_rules():
    s.check_stock(5, 5)
    assert raises(s.check_stock, 6, 5)
    assert raises(s.check_stock, 1, 0)
    assert raises(s.check_stock, 1, None)
    assert s.clean_stock("59") == 59
    for bad in ("0", "-1", "1.5", "abc", ""):
        assert raises(s.clean_stock, bad), bad


def test_units_and_input_rules():
    assert s.clean_unit(" KG ") == "kg"
    assert raises(s.clean_unit, "<script>")
    assert s.clean_email("  Alex@Example.COM ") == "alex@example.com"
    assert raises(s.clean_email, "nope")
    assert raises(s.clean_username, "<img src=x onerror=alert(1)>")
    assert s.clean_username("joy gakii") == "joy gakii"                  # existing users still valid
    assert raises(s.check_password, "short")
    s.check_password("longenough1")


def test_phone_and_payment_numbers():
    assert s.normalize_kenyan_phone("0712 345 678") == "254712345678"
    assert s.normalize_kenyan_phone("+254 112 345 678") == "254112345678"
    assert s.normalize_kenyan_phone("12345") is None
    assert s.clean_payment_number("till", "123 456") == "123456"
    assert raises(s.clean_payment_number, "till", "12")
    assert raises(s.clean_payment_method, "paypal")


def test_image_detection():
    assert s.detect_image_ext(b"\xff\xd8\xff\xe0abc") == ".jpg"
    assert s.detect_image_ext(b"\x89PNG\r\n\x1a\nxx") == ".png"
    assert s.detect_image_ext(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"
    assert raises(s.detect_image_ext, b"<html><script>alert(1)</script>")
    assert raises(s.detect_image_ext, b"")


def test_legacy_parsing():
    assert s.parse_legacy_price("90(per kg)") == (Decimal("90.00"), "kg")
    assert s.parse_legacy_price("KES 1,200 per bag") == (Decimal("1200.00"), "bag")
    assert s.parse_legacy_price("12.5/litre") == (Decimal("12.50"), "litre")
    assert s.parse_legacy_price("free") == (None, "kg")
    assert s.parse_legacy_price(None) == (None, "kg")
    assert s.parse_legacy_quantity("59") == 59
    assert s.parse_legacy_quantity("100kg") == 100
    assert s.parse_legacy_quantity("lots") is None


# ---------- payment verification ----------
def test_completed_payment_marks_order_paid_and_reduces_stock():
    payment, order, product = make()
    db = FakeDB()
    assert s.settle_payment(db, payment, GOOD) == "completed"
    assert order.status == "paid" and order.paid_at
    assert product.stock == 8
    assert payment.confirmation_code == "ABC123" and payment.payment_method == "MpesaKE"
    assert db.commits == 1


def test_settling_twice_is_harmless():
    payment, order, product = make()
    db = FakeDB()
    s.settle_payment(db, payment, GOOD)
    s.settle_payment(db, payment, GOOD)
    assert product.stock == 8, "stock must only drop once (IPN + return page can both fire)"
    assert order.status == "paid"


def test_underpayment_is_not_accepted():
    payment, order, _ = make()
    status = dict(GOOD, amount=1.0)                                      # paid KES 1 for a KES 180 order
    assert s.settle_payment(FakeDB(), payment, status) == "review"
    assert order.status == "pending"


def test_wrong_reference_or_currency_is_not_accepted():
    payment, order, _ = make()
    assert s.settle_payment(FakeDB(), payment, dict(GOOD, merchant_reference="SHAMBA-99-zzzzzzzz")) == "review"
    assert order.status == "pending"
    payment, order, _ = make()
    assert s.settle_payment(FakeDB(), payment, dict(GOOD, currency="USD")) == "review"
    assert order.status == "pending"


def test_overpayment_is_accepted():
    payment, order, _ = make()
    assert s.settle_payment(FakeDB(), payment, dict(GOOD, amount=200.0)) == "completed"
    assert order.status == "paid"


def test_unpaid_and_failed_states():
    payment, order, _ = make()
    pending = {"payment_status_description": "Invalid", "status_code": 0}
    assert s.settle_payment(FakeDB(), payment, pending) == "pending"
    assert order.status == "pending"
    assert s.settle_payment(FakeDB(), payment, {"payment_status_description": "Failed", "status_code": 2}) == "failed"
    assert order.status == "pending", "a failed attempt leaves the order open so the customer can retry"
    assert s.settle_payment(FakeDB(), payment, GOOD) == "completed", "a retry that succeeds still works"
    assert order.status == "paid"


def test_status_code_only_and_junk_answers():
    payment, order, _ = make()
    assert s.evaluate_status(payment, {"status_code": 1}) == "completed"
    assert s.evaluate_status(payment, {}) == "pending"
    assert s.evaluate_status(payment, {"payment_status_description": "Completed", "amount": "abc"}) == "review"


def test_reversal_refunds_order():
    payment, order, _ = make()
    s.settle_payment(FakeDB(), payment, GOOD)
    assert s.settle_payment(FakeDB(), payment, {"payment_status_description": "Reversed", "status_code": 3}) == "reversed"
    assert order.status == "refunded"
    assert s.settle_payment(FakeDB(), payment, GOOD) == "reversed", "a reversed payment can't come back"


def test_stock_never_goes_negative():
    payment, order, product = make(stock=1, qty=5)
    s.settle_payment(FakeDB(), payment, GOOD)
    assert product.stock == 0


def test_delivered_order_is_not_reopened():
    payment, order, product = make(order_status="delivered")
    s.settle_payment(FakeDB(), payment, GOOD)
    assert order.status == "delivered" and product.stock == 10


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS  {name}")
    print(f"\n{len(tests)} tests passed")
