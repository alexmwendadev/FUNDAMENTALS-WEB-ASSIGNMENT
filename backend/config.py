"""Central settings. Everything that differs between my laptop and the
live server comes from environment variables (see .env.example)."""
# standard library tools: logging for messages, os to read environment variables,
# secrets to make random keys, Path to work with the .secret_key file
import logging
import os
import secrets
from pathlib import Path

# python-dotenv reads the .env file and turns its lines into environment variables
from dotenv import load_dotenv

# load .env straight away so every setting below can see its values
load_dotenv()
# logger I use for startup warnings (they appear in the uvicorn console)
log = logging.getLogger("shamba")


# turns "a, b, c" into ['a', 'b', 'c'] with spaces and trailing slashes removed (used for the CORS list)
def _csv(value):
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]


# works out the secret key that signs login tokens
def _load_secret_key():
    """Use SECRET_KEY from the environment. If it is missing, create a random
    one once and keep it in .secret_key (git-ignored) so logins survive restarts."""
    # first choice: SECRET_KEY from the environment / .env
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    # second choice: a key saved earlier in a local file
    path = Path(".secret_key")
    # the file is there, so reuse its key
    if path.exists():
        return path.read_text().strip()
    # no key anywhere yet: make a long random one and save it so logins survive a restart
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    # tell me in the console that a key was generated
    log.warning("SECRET_KEY is not set. Generated one and saved it to .secret_key. "
                "Set SECRET_KEY in your hosting environment for production.")
    return key


# the key used to sign (and later verify) login tokens
SECRET_KEY = _load_secret_key()
# how long a login stays valid, in minutes (default 60)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# where the database lives; defaults to a local SQLite file called shamba.db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shamba.db").strip()
# older hosts hand out 'postgres://' but SQLAlchemy needs 'postgresql://', so convert it
if DATABASE_URL.startswith("postgres://"):  # some hosts still hand out the old scheme
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# Where the website (HTML/JS) is served from. Pesapal sends customers back here.
# no trailing slash so I can safely add paths like /payment-return.html
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000").strip().rstrip("/")
# Public https address of THIS API (my tunnel or live domain). Pesapal calls it.
PUBLIC_BASE_URL = os.getenv("PESAPAL_PUBLIC_BASE_URL", "").strip().rstrip("/")

# websites allowed to call this API from a browser (CORS). Falls back to the two local addresses
CORS_ORIGINS = _csv(os.getenv("CORS_ORIGINS", "")) or ["http://localhost:8000", "http://127.0.0.1:8000"]
# the website's own address is always allowed
if FRONTEND_URL not in CORS_ORIGINS:
    CORS_ORIGINS.append(FRONTEND_URL)

# Pesapal. Anything other than "live"/"production" is treated as sandbox, so a typo can't charge real money.
# 'sandbox' (test money) or 'live' (real money), read from .env
PESAPAL_ENVIRONMENT = os.getenv("PESAPAL_ENVIRONMENT", "sandbox").strip().lower()
# True only for 'live' or 'production'
PESAPAL_LIVE = PESAPAL_ENVIRONMENT in ("live", "production")
# everything else counts as sandbox, so a typo can never charge real money
PESAPAL_SANDBOX = not PESAPAL_LIVE
# API credentials from the Pesapal dashboard
PESAPAL_CONSUMER_KEY = os.getenv("PESAPAL_CONSUMER_KEY", "").strip()
PESAPAL_CONSUMER_SECRET = os.getenv("PESAPAL_CONSUMER_SECRET", "").strip()
# id Pesapal gave back when I registered my notification URL (see register_ipn.py)
PESAPAL_IPN_ID = os.getenv("PESAPAL_IPN_ID", "").strip()
# Used only for customers who have no email on their account yet.
PESAPAL_FALLBACK_EMAIL = os.getenv("PESAPAL_FALLBACK_EMAIL", "customer@example.com").strip()

# folder for uploaded images when Cloudinary is not used
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
# when this is set, images go to Cloudinary instead of the local disk
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "").strip()  # cloudinary://key:secret@cloud_name
# upload size limits: 5 MB for product photos, 2 MB for profile pictures
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AVATAR_BYTES = 2 * 1024 * 1024

# safety warning: real-money mode while the site is still on localhost
if PESAPAL_LIVE and FRONTEND_URL.startswith("http://localhost"):
    log.warning("PESAPAL_ENVIRONMENT is LIVE while FRONTEND_URL is localhost: "
                "test purchases will charge real money.")
