from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    EmailCodeRequest,
    EmailCodeResponse,
    EmailOnlyRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.audit import log_event, notify_user
from app.services.email_codes import (
    EMAIL_VERIFICATION,
    PASSWORD_RESET,
    send_password_reset_code,
    send_verification_code,
    verify_email_code,
)
from app.services.quota import get_or_create_active_subscription


router = APIRouter()


def _email_code_response(email: str) -> EmailCodeResponse:
    return EmailCodeResponse(email=email, expires_in_minutes=get_settings().email_code_expire_minutes)


@router.post("/register", response_model=EmailCodeResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> EmailCodeResponse:
    email = payload.email.lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this email already exists")

    users_count = db.scalar(select(func.count()).select_from(User)) or 0
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ADMIN.value if users_count == 0 else UserRole.USER.value,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.flush()
    get_or_create_active_subscription(db, user)
    send_verification_code(db, user=user)
    log_event(
        db,
        event_type="user.registered",
        target_user=user,
        entity_type="user",
        entity_id=user.id,
        message="New user registered",
        payload={"role": user.role},
        request=request,
    )
    db.commit()
    return _email_code_response(user.email)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    if not user.is_verified:
        send_verification_code(db, user=user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified. Verification code was sent.",
        )
    log_event(
        db,
        event_type="user.login",
        actor_user=user,
        target_user=user,
        entity_type="user",
        entity_id=user.id,
        message="User logged in",
        request=request,
    )
    db.commit()
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=user)


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(payload: EmailCodeRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already verified")
    item = verify_email_code(db, email=email, purpose=EMAIL_VERIFICATION, code=payload.code)
    if item is None:
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification code")
    user.is_verified = True
    log_event(
        db,
        event_type="user.email_verified",
        actor_user=user,
        target_user=user,
        entity_type="user",
        entity_id=user.id,
        message="User verified email",
        request=request,
    )
    notify_user(
        db,
        user=user,
        type="user.welcome",
        title="Добро пожаловать",
        body="Email подтвержден. Теперь можно запускать парсеры и смотреть результаты в личном кабинете.",
    )
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=user)


@router.post("/resend-verification", response_model=EmailCodeResponse)
def resend_verification(payload: EmailOnlyRequest, db: Session = Depends(get_db)) -> EmailCodeResponse:
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.is_active and not user.is_verified:
        send_verification_code(db, user=user)
        db.commit()
    return _email_code_response(email)


@router.post("/password-reset/request", response_model=EmailCodeResponse)
def request_password_reset(payload: EmailOnlyRequest, db: Session = Depends(get_db)) -> EmailCodeResponse:
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.is_active:
        send_password_reset_code(db, user=user)
        db.commit()
    return _email_code_response(email)


@router.post("/password-reset/confirm", response_model=TokenResponse)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset code")
    item = verify_email_code(db, email=email, purpose=PASSWORD_RESET, code=payload.code)
    if item is None:
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset code")
    user.password_hash = hash_password(payload.new_password)
    user.is_verified = True
    log_event(
        db,
        event_type="user.password_reset",
        actor_user=user,
        target_user=user,
        entity_type="user",
        entity_id=user.id,
        message="User reset password by email code",
        request=request,
    )
    notify_user(
        db,
        user=user,
        type="security.password_reset",
        title="Пароль восстановлен",
        body="Пароль аккаунта был изменен через код на почту.",
        payload={},
    )
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=user)
