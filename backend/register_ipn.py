"""One-time setup: tell Pesapal where to send payment notifications.

    1. Set PESAPAL_PUBLIC_BASE_URL in .env to my public https address
       (the Cloudflare tunnel while developing, the real domain in production).
    2. Run:  python register_ipn.py
    3. Copy the printed PESAPAL_IPN_ID line into .env and restart the server.

The IPN id is different for sandbox and live, and it is tied to that URL:
if the tunnel address changes, run this again."""
# sys.exit stops the script with a message
import sys

# my settings (keys, public URL, sandbox/live)
import config
# the wrapper that talks to Pesapal
import pesapal_service

# Pesapal only accepts a public https address, so stop early if it isn't set
if not config.PUBLIC_BASE_URL.startswith("https://"):
    sys.exit("Set PESAPAL_PUBLIC_BASE_URL in .env to a public https:// address first.")

# the notification address Pesapal will call when a payment changes
url = f"{config.PUBLIC_BASE_URL}/api/pesapal/ipn"
# just for the message below, so I can see which mode I'm registering in
mode = "LIVE" if config.PESAPAL_LIVE else "sandbox"
# show what is about to happen
print(f"Registering {url} with Pesapal ({mode})...")

# ask Pesapal to register the address
try:
    # 'POST' means Pesapal will send the notification as a POST request
    result = pesapal_service.register_ipn(url, "POST")
# registration failed
except pesapal_service.PaymentGatewayError as exc:
    # show the reason and stop
    sys.exit(str(exc))

# show Pesapal's whole reply
print(result)
# pull out the id Pesapal gave back
ipn_id = result.get("ipn_id") if hasattr(result, "get") else None
# found it: print the exact line to paste into .env
if ipn_id:
    print(f"\nAdd this to your .env:\nPESAPAL_IPN_ID={ipn_id}")
# not found: the reply above has to be read by hand
else:
    print("\nCould not find ipn_id in the reply above. Check it and add PESAPAL_IPN_ID to .env by hand.")
