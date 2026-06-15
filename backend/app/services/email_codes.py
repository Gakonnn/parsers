from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import EmailCode
from app.models.user import User
from app.services.mailer import send_email


logger = logging.getLogger(__name__)

EMAIL_VERIFICATION = "email_verification"
PASSWORD_RESET = "password_reset"
MAX_CODE_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(*, email: str, purpose: str, code: str) -> str:
    settings = get_settings()
    message = f"{_normalize_email(email)}:{purpose}:{code.strip()}".encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _expire_existing(db: Session, *, email: str, purpose: str) -> None:
    items = db.scalars(
        select(EmailCode).where(
            EmailCode.email == _normalize_email(email),
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
    ).all()
    now = _now()
    for item in items:
        item.consumed_at = now


def create_email_code(db: Session, *, user: User | None, email: str, purpose: str) -> tuple[EmailCode, str]:
    normalized_email = _normalize_email(email)
    code = _new_code()
    settings = get_settings()
    _expire_existing(db, email=normalized_email, purpose=purpose)
    item = EmailCode(
        user_id=user.id if user else None,
        email=normalized_email,
        purpose=purpose,
        code_hash=_hash_code(email=normalized_email, purpose=purpose, code=code),
        expires_at=_now() + timedelta(minutes=settings.email_code_expire_minutes),
    )
    db.add(item)
    return item, code


def verify_email_code(db: Session, *, email: str, purpose: str, code: str) -> EmailCode | None:
    normalized_email = _normalize_email(email)
    now = _now()
    item = db.scalar(
        select(EmailCode)
        .where(
            EmailCode.email == normalized_email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
            EmailCode.expires_at > now,
        )
        .order_by(EmailCode.created_at.desc())
    )
    if item is None:
        return None
    if item.attempts >= MAX_CODE_ATTEMPTS:
        item.consumed_at = now
        return None
    item.attempts += 1
    expected = _hash_code(email=normalized_email, purpose=purpose, code=code)
    if not hmac.compare_digest(item.code_hash, expected):
        return None
    item.consumed_at = now
    return item


def send_verification_code(db: Session, *, user: User) -> None:
    _, code = create_email_code(db, user=user, email=user.email, purpose=EMAIL_VERIFICATION)
    _send_code_email(email=user.email, code=code, purpose=EMAIL_VERIFICATION)


def send_password_reset_code(db: Session, *, user: User) -> None:
    _, code = create_email_code(db, user=user, email=user.email, purpose=PASSWORD_RESET)
    _send_code_email(email=user.email, code=code, purpose=PASSWORD_RESET)


def _send_code_email(*, email: str, code: str, purpose: str) -> None:
    settings = get_settings()
    if purpose == PASSWORD_RESET:
        title = "Код восстановления пароля DataLeadHub"
        lead = "Для восстановления пароля введите этот код на сайте:"
    else:
        title = "Код подтверждения DataLeadHub"
        lead = "Для подтверждения email введите этот код на сайте:"
    text = (
        f"{lead}\n\n"
        f"{code}\n\n"
        f"Код действует {settings.email_code_expire_minutes} минут. "
        "Если вы не запрашивали это письмо, просто проигнорируйте его."
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#0f172a">
      <p>{lead}</p>
      <div style="font-size:32px;font-weight:700;letter-spacing:8px;margin:18px 0;color:#0b63f6">{code}</div>
      <p style="color:#64748b">Код действует {settings.email_code_expire_minutes} минут.</p>
      <p style="color:#64748b">Если вы не запрашивали это письмо, просто проигнорируйте его.</p>
    </div>
    """
    send_email(to_email=email, subject=title, text=text, html=html)
    logger.info("Email code sent: purpose=%s email=%s", purpose, email)
