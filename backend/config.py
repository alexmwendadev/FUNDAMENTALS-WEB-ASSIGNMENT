"""Central settings. Everything that differs between my laptop and the
live server comes from environment variables (see .env.example)."""
import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("shamba")

def _csv(value):
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]

def _load_secret_key():
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    path = Path(".secret_key")
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    log.warning("SECRET_KEY is not set. Generated one and saved it to .secret_key. "
                "Set SECRET_KEY in your hosting environment for production.")
    return key

SECRET_KEY = _load_secret_key()
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shamba.db").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000").strip().rstrip("/")
PUBLIC_BASE_URL = os.getenv("PESAPAL_PUBLIC_BASE_URL", "").strip().rstrip("/")

CORS_ORIGINS = _csv(os.getenv("CORS_ORIGINS", "")) or ["http://localhost:8000", "http://127.0.0.1:8000"]
if FRONTEND_URL not in CORS_ORIGINS:
    CORS_ORIGINS.append(FRONTEND_URL)

PESAPAL_ENVIRONMENT = os.getenv("PESAPAL_ENVIRONMENT", "sandbox").strip().lower()
PESAPAL_LIVE = PESAPAL_ENVIRONMENT in ("live", "production")
PESAPAL_SANDBOX = not PESAPAL_LIVE
PESAPAL_CONSUMER_KEY = os.getenv("PESAPAL_CONSUMER_KEY", "").strip()
PESAPAL_CONSUMER_SECRET = os.getenv("PESAPAL_CONSUMER_SECRET", "").strip()
PESAPAL_IPN_ID = os.getenv("PESAPAL_IPN_ID", "").strip()
PESAPAL_FALLBACK_EMAIL = os.getenv("PESAPAL_FALLBACK_EMAIL", "customer@example.com").strip()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "").strip()
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AVATAR_BYTES = 2 * 1024 * 1024

# --- NEW: Brevo Email Configuration ---
# API key from your Brevo dashboard (Settings -> SMTP & API -> API Keys)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
# The verified sender email address you set up in Brevo (e.g. your gmail or a custom domain email)
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "noreply@shambafresh.com").strip()

if PESAPAL_LIVE and FRONTEND_URL.startswith("http://localhost"):
    log.warning("PESAPAL_ENVIRONMENT is LIVE while FRONTEND_URL is localhost: "
                "test purchases will charge real money.")