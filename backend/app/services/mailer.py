from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings


logger = logging.getLogger(__name__)


def _sender() -> tuple[str, str]:
    settings = get_settings()
    address = settings.smtp_from_email or settings.smtp_username
    name = settings.smtp_from_name or "DataLeadHub"
    return name, address


def send_email(*, to_email: str, subject: str, text: str, html: str | None = None) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        logger.warning("SMTP is not configured. Email to %s skipped. Subject: %s", to_email, subject)
        return

    from_name, from_email = _sender()
    if not from_email:
        logger.warning("SMTP sender is not configured. Email to %s skipped.", to_email)
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=20) as server:
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls(context=context)
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
