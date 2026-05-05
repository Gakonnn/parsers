from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.audit import log_event, notify_user
from app.services.quota import get_or_create_active_subscription


router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
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
    )
    db.add(user)
    db.flush()
    get_or_create_active_subscription(db, user)
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
    notify_user(
        db,
        user=user,
        type="user.welcome",
        title="Добро пожаловать",
        body="Аккаунт создан. Теперь можно запускать парсеры и смотреть результаты в личном кабинете.",
    )
    db.commit()
    db.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
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
