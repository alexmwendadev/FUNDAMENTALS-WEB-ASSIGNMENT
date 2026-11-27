import requests
import config
import logging

log = logging.getLogger("shamba")

def send_reset_email(to_email, reset_link):
    """Sends a beautifully styled password reset email using Brevo API."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": config.BREVO_API_KEY,
        "content-type": "application/json"
    }
    
    # The logo must be a public URL (using your deployed frontend URL)
    logo_url = f"{config.FRONTEND_URL}/assets/images/shambafreshlogo.jpg"
    
    # Industry-standard HTML email (uses tables and inline CSS for maximum compatibility)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reset Your Password</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f6f1; font-family: 'Figtree', 'Segoe UI', Arial, sans-serif; -webkit-font-smoothing: antialiased;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f4f6f1; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <!-- Main Card -->
                    <table width="100%" max-width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); max-width: 600px; width: 100%;">
                        
                        <!-- Header with Logo and Brand Color -->
                        <tr>
                            <td align="center" style="background-color: #2c5a37; padding: 30px 20px;">
                                <img src="{logo_url}" alt="Shamba Fresh Logo" width="80" style="display: block; border-radius: 12px; margin-bottom: 10px;">
                                <h1 style="color: #ffffff; font-size: 24px; margin: 0; font-weight: 800; letter-spacing: -0.5px;">Shamba Fresh</h1>
                            </td>
                        </tr>

                        <!-- Body Content -->
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h2 style="color: #33261d; font-size: 20px; margin-top: 0; margin-bottom: 16px; font-weight: 700;">Password Reset Request</h2>
                                <p style="color: #555555; font-size: 16px; line-height: 1.6; margin-bottom: 24px;">
                                    Hello,
                                </p>
                                <p style="color: #555555; font-size: 16px; line-height: 1.6; margin-bottom: 30px;">
                                    We received a request to reset the password for your Shamba Fresh account. Click the button below to choose a new password.
                                </p>
                                
                                <!-- Bulletproof Button -->
                                <table border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 30px;">
                                    <tr>
                                        <td align="center" style="border-radius: 999px;" bgcolor="#2c5a37">
                                            <a href="{reset_link}" target="_blank" style="font-size: 16px; font-family: 'Figtree', Arial, sans-serif; color: #ffffff; text-decoration: none; padding: 14px 30px; border-radius: 999px; border: 2px solid #2c5a37; display: inline-block; font-weight: bold;">
                                                Reset My Password
                                            </a>
                                        </td>
                                    </tr>
                                </table>

                                <p style="color: #777777; font-size: 14px; line-height: 1.6; margin-bottom: 10px;">
                                    If the button doesn't work, copy and paste this link into your browser:
                                </p>
                                <p style="color: #2c5a37; font-size: 14px; line-height: 1.6; word-break: break-all; margin-bottom: 30px;">
                                    <a href="{reset_link}" style="color: #2c5a37;">{reset_link}</a>
                                </p>

                                <hr style="border: none; border-top: 1px solid #eaeaea; margin-bottom: 24px;">

                                <p style="color: #999999; font-size: 14px; line-height: 1.6; margin-bottom: 0;">
                                    <strong>Didn't request this?</strong> If you did not make this request, you can safely ignore this email. Your password will not be changed until you access the link above and create a new one. This link expires in 1 hour.
                                </p>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td align="center" style="background-color: #f9fbf6; padding: 20px; border-top: 1px solid #eaeaea;">
                                <p style="color: #999999; font-size: 12px; margin: 0; line-height: 1.5;">
                                    &copy; 2026 Shamba Fresh. All rights reserved.<br>
                                    Tharaka-Nithi, Kenya
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": "Shamba Fresh", "email": config.BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": "Reset Your Shamba Fresh Password",
        "htmlContent": html_content
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return True
    except Exception as exc:
        log.error(f"Brevo email error: {exc}")
        return False