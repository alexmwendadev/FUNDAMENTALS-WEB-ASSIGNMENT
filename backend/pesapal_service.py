"""Thin wrapper around the pesapal SDK so the rest of the app never touches it
directly. The SDK is imported lazily, so the server still starts without keys."""
# logging for errors, Decimal so the amount is sent to Pesapal exactly
import logging
from decimal import Decimal

# my settings (keys, sandbox/live switch, IPN id)
import config

# shared logger
log = logging.getLogger("shamba")


# the one error type for anything that goes wrong with Pesapal, so main.py only has to catch this
class PaymentGatewayError(Exception):
    """Pesapal could not be reached, rejected the request, or isn't configured."""


# the Pesapal client is created on first use and then reused
_client = None


# returns the shared Pesapal client, creating it the first time
def _get_client():
    # so the assignment below changes the module-level variable
    global _client
    # not created yet
    if _client is None:
        # no keys in .env: say so clearly instead of failing later
        if not (config.PESAPAL_CONSUMER_KEY and config.PESAPAL_CONSUMER_SECRET):
            raise PaymentGatewayError("PESAPAL_CONSUMER_KEY / PESAPAL_CONSUMER_SECRET are not set")
        # the SDK is imported here (not at the top) so the server still starts when the SDK or keys are missing
        try:
            # the unofficial Pesapal SDK
            from pesapal import PesapalClient
            # log in to Pesapal with my keys
            _client = PesapalClient(
                consumer_key=config.PESAPAL_CONSUMER_KEY,
                consumer_secret=config.PESAPAL_CONSUMER_SECRET,
                # True sends test traffic, False sends real money traffic
                sandbox=config.PESAPAL_SANDBOX,
            )
        # wrap any SDK failure in my own error type
        except Exception as exc:
            raise PaymentGatewayError(f"Could not start the Pesapal client: {exc}") from exc
    # hand back the ready client
    return _client


# creates the order on Pesapal and returns {'tracking_id', 'redirect_url'}.
# The customer is then sent to redirect_url to pay (M-Pesa, card...)
def start_checkout(*, merchant_reference, amount, description, callback_url,
                   email, phone, first_name, address):
    """Create the order on Pesapal. Returns {'tracking_id', 'redirect_url'}.
    The customer is sent to redirect_url to choose M-Pesa, card, etc."""
    # Pesapal needs the id of my registered notification URL; stop with a clear message if it's missing
    if not config.PESAPAL_IPN_ID:
        raise PaymentGatewayError("PESAPAL_IPN_ID is not set. Run: python register_ipn.py")
    # get the shared client
    client = _get_client()
    # everything below talks to Pesapal, so any failure becomes a PaymentGatewayError
    try:
        # SDK classes used to describe the order
        from pesapal import BillingAddress, OrderRequest
        # the order as Pesapal wants it
        request = OrderRequest(
            # my own unique reference for this payment attempt
            id=merchant_reference,
            # Kenyan shillings
            currency="KES",
            # the total worked out on the server
            amount=Decimal(str(amount)),
            # shown to the customer on Pesapal's page; Pesapal allows 100 characters at most
            description=description[:100],
            # where Pesapal sends the customer after paying
            callback_url=callback_url,
            # which registered IPN (notification URL) Pesapal should call
            notification_id=config.PESAPAL_IPN_ID,
            # contact details Pesapal requires
            billing_address=BillingAddress(
                # receipt email
                email_address=email,
                # customer's phone
                phone_number=phone,
                # Kenya
                country_code="KE",
                # username stands in for a first name; capped at 50 characters, with a fallback
                first_name=first_name[:50] or "Customer",
                # Pesapal wants a last name, a placeholder is enough
                last_name="Customer",
                # delivery location as the address line
                line1=address[:200],
            ),
        )
        # send the order to Pesapal
        submitted = client.submit_order(request)
        # keep only the two values I need from Pesapal's reply
        return {"tracking_id": submitted["order_tracking_id"], "redirect_url": submitted["redirect_url"]}
    # Pesapal rejected the order or couldn't be reached
    except Exception as exc:
        # `from exc` keeps the original error visible in the logs
        raise PaymentGatewayError(f"Pesapal rejected the order: {exc}") from exc


# asks Pesapal directly what happened to a payment. This answer is the only thing I trust
def fetch_status(tracking_id):
    """Ask Pesapal directly what happened. This is the only thing we trust."""
    # get the shared client
    client = _get_client()
    # same pattern: failures become PaymentGatewayError
    try:
        # convert the reply to a plain dictionary
        return dict(client.get_transaction_status(tracking_id))
    # couldn't read the status
    except Exception as exc:
        raise PaymentGatewayError(f"Could not read the payment status: {exc}") from exc


# tells Pesapal which URL to call when a payment changes (used once by register_ipn.py)
def register_ipn(url, method="POST"):
    client = _get_client()
    try:
        return client.register_ipn(url, method)
    except Exception as exc:
        raise PaymentGatewayError(f"Could not register the IPN URL: {exc}") from exc
