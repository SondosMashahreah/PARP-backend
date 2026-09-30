import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_otp_email(to_email: str, otp: str) -> None:
    if not settings.MAIL_HOST or not settings.MAIL_FROM:
        raise RuntimeError("Mailbox SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = "PARP verification code"
    message["From"] = settings.MAIL_FROM
    message["To"] = to_email
    message.set_content(
        f"Your PARP verification code is {otp}. "
        f"It expires in {settings.OTP_EXPIRE_MINUTES} minutes."
    )

    with smtplib.SMTP(settings.MAIL_HOST, settings.MAIL_PORT, timeout=20) as smtp:
        if settings.MAIL_STARTTLS:
            smtp.starttls()
        if settings.MAIL_USERNAME:
            smtp.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        smtp.send_message(message)
