from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, UserProfileUpdate, UserPublic
from app.services.audit import log_event, notify_user


router = APIRouter()


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserPublic)
def update_current_user(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return current_user
    for key, value in updates.items():
        setattr(current_user, key, value)
    log_event(
        db,
        event_type="user.profile_updated",
        actor_user=current_user,
        target_user=current_user,
        entity_type="user",
        entity_id=current_user.id,
        message="User updated own profile",
        payload={"updated_fields": sorted(updates.keys())},
    )
    notify_user(
        db,
        user=current_user,
        type="profile.updated",
        title="Профиль обновлен",
        body="Изменения профиля сохранены.",
        payload={"updated_fields": sorted(updates.keys())},
    )
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/password")
def change_current_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    user = db.scalar(select(User).where(User.id == current_user.id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    log_event(
        db,
        event_type="user.password_changed",
        actor_user=user,
        target_user=user,
        entity_type="user",
        entity_id=user.id,
        message="User changed own password",
        payload={},
    )
    notify_user(
        db,
        user=user,
        type="security.password_changed",
        title="Пароль изменен",
        body="Пароль аккаунта был обновлен.",
        payload={},
    )
    db.commit()
    return {"ok": True}
