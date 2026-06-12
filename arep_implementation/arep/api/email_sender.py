"""
ORION Email Sender.

When SMTP is configured (SMTP_HOST + SMTP_FROM env vars set): sends real email.
When not configured: logs the reset link to the console so dev/beta mode still works.
"""
from __future__ import annotations

import smtplib
import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from arep.config.env import get_settings
from arep.utils.logging_config import get_logger

logger = get_logger("email")


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """
    Send a password reset email.

    If SMTP is not configured, logs the link at WARNING level so you can
    copy-paste it during development or beta testing without any email setup.
    """
    settings = get_settings()

    subject = "Reset your ORION password"
    body_text = textwrap.dedent(f"""
        Hi,

        Someone requested a password reset for your ORION account ({to_email}).

        Click the link below to set a new password (valid for {settings.reset_token_ttl_minutes} minutes):

            {reset_link}

        If you did not request this, you can safely ignore this email.
        Your password will not change unless you click the link above.

        -- The ORION team
    """).strip()

    body_html = f"""
    <html><body style="font-family:sans-serif;color:#222;max-width:520px;margin:40px auto">
      <h2 style="color:#1a1a2e">Reset your ORION password</h2>
      <p>Someone requested a password reset for your ORION account (<strong>{to_email}</strong>).</p>
      <p>Click the button below to set a new password
         (valid for <strong>{settings.reset_token_ttl_minutes} minutes</strong>):</p>
      <p style="text-align:center;margin:32px 0">
        <a href="{reset_link}"
           style="background:#4f46e5;color:#fff;padding:12px 28px;
                  border-radius:6px;text-decoration:none;font-weight:600">
          Reset Password
        </a>
      </p>
      <p style="color:#666;font-size:13px">Or copy this link:<br>
         <a href="{reset_link}" style="color:#4f46e5">{reset_link}</a></p>
      <p style="color:#999;font-size:12px">
        If you did not request this, ignore this email.
        Your password will not change.
      </p>
    </body></html>
    """

    if not settings.email_enabled:
        # Dev/beta fallback: log the link so you can still test the flow
        logger.warning(
            "SMTP not configured — password reset link for %s: %s",
            to_email, reset_link,
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        if settings.smtp_use_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)

        if settings.smtp_user and settings.smtp_pass:
            server.login(settings.smtp_user, settings.smtp_pass)

        server.sendmail(settings.smtp_from, [to_email], msg.as_string())
        server.quit()
        logger.info("Password reset email sent to %s", to_email)

    except Exception as exc:
        logger.error("Failed to send reset email to %s: %s", to_email, exc)
        raise
