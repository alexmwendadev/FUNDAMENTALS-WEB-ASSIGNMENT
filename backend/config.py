"""Central settings. Everything that differs between my laptop and the
live server comes from environment variables (see .env.example)."""
# logging = warnings, os = environment variables, secrets = random keys, Path = file paths
import logging
import os
import secrets
from pathlib import Path

# reads the .env file so secrets stay out of the code
from dotenv import load_dotenv

# load everything from .env into environment variables
load_dotenv()
# shared logger named 'shamba'
log = logging.getLogger("shamba")

# 'a, b, c' becomes ['a', 'b', 'c'] with spaces and trailing slashes removed (used for the allowed-origins list)
def _csv(value):
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]

# finds the key that signs login tokens: the environment first, then the .secret_key file, otherwise it makes a new one
def _load_secret_key():
    # 1. an environment variable (best, used in production)
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    # 2. a file saved by an earlier run
    path = Path(".secret_key")
    if path.exists():
        return path.read_text().strip()
    # 3. neither exists: make a new random key and save it so logins survive a restart
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    log.warning("SECRET_KEY is not set. Generated one and saved it to .secret_key. "
                "Set SECRET_KEY in your hosting environment for production.")
    return key

# the signing key used by auth.py
SECRET_KEY = _load_secret_key()
# how long a login lasts (default 60 minutes)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# where the database lives; falls back to a local SQLite file for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shamba.db").strip()
# some hosts give 'postgres://' but SQLAlchemy needs 'postgresql://', so I fix the start
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# the address of my website; used in email links and as Pesapal's return page
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000").strip().rstrip("/")
# the public address of this API (Pesapal's IPN needs it)
PUBLIC_BASE_URL = os.getenv("PESAPAL_PUBLIC_BASE_URL", "").strip().rstrip("/")

# websites allowed to call this API from a browser
CORS_ORIGINS = _csv(os.getenv("CORS_ORIGINS", "")) or ["http://localhost:8000", "http://127.0.0.1:8000"]
# the frontend must always be allowed
if FRONTEND_URL not in CORS_ORIGINS:
    CORS_ORIGINS.append(FRONTEND_URL)

# 'sandbox' = pretend payments, 'live' = real money
PESAPAL_ENVIRONMENT = os.getenv("PESAPAL_ENVIRONMENT", "sandbox").strip().lower()
# True only for live / production
PESAPAL_LIVE = PESAPAL_ENVIRONMENT in ("live", "production")
# the opposite of live
PESAPAL_SANDBOX = not PESAPAL_LIVE
# my Pesapal login details (from .env, never written in the code)
PESAPAL_CONSUMER_KEY = os.getenv("PESAPAL_CONSUMER_KEY", "").strip()
PESAPAL_CONSUMER_SECRET = os.getenv("PESAPAL_CONSUMER_SECRET", "").strip()
# the id of the registered IPN address (made by register_ipn.py)
PESAPAL_IPN_ID = os.getenv("PESAPAL_IPN_ID", "").strip()
# used when a buyer has no email, because Pesapal insists on one
PESAPAL_FALLBACK_EMAIL = os.getenv("PESAPAL_FALLBACK_EMAIL", "customer@example.com").strip()

# folder for images saved locally
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
# if this is set, images go to Cloudinary instead of the local folder
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "").strip()
# upload limits: 5 MB for product photos...
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
# ...and 2 MB for profile pictures
MAX_AVATAR_BYTES = 2 * 1024 * 1024

# --- NEW: Brevo Email Configuration ---
# API key from your Brevo dashboard (Settings -> SMTP & API -> API Keys)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
# The verified sender email address you set up in Brevo (e.g. your gmail or a custom domain email)
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "noreply@shambafresh.com").strip()

# warns me if I'm about to test with real money from my laptop
if PESAPAL_LIVE and FRONTEND_URL.startswith("http://localhost"):
    log.warning("PESAPAL_ENVIRONMENT is LIVE while FRONTEND_URL is localhost: "
                "test purchases will charge real money.")