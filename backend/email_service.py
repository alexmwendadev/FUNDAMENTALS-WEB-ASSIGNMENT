import requests
import config
import logging

log = logging.getLogger("shamba")

def send_reset_email(to_email, reset_link):
    """Sends a password reset email using Brevo API."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": config.BREVO_API_KEY,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "Shamba Fresh", "email": config.BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": "Reset Your Shamba Fresh Password",
        "htmlContent": f"""
            <h2>Password Reset</h2>
            <p>You requested a password reset. Click the link below to set a new password:</p>
            <a href="{reset_link}" style="background:#2c5a37;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;">Reset Password</a>
            <p>If you didn't request this, you can safely ignore this email.</p>
        """
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return True
    except Exception as exc:
        log.error(f"Brevo email error: {exc}")
        return False