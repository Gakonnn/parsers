from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.system import SupportMessage
from app.models.user import User, UserRole
from app.schemas.system import SupportMessageCreate, SupportMessagePublic
from app.services.audit import log_event, notify_user


router = APIRouter()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


@router.post("/messages", response_model=SupportMessagePublic, status_code=status.HTTP_201_CREATED)
def create_support_message(
    payload: SupportMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> SupportMessage:
    name = _clean(payload.name)
    email = _clean(payload.email)
    message = _clean(payload.message)
    if not name or not email or not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name, email and message are required")

    item = SupportMessage(
        name=name,
        email=email.lower(),
        phone=_clean(payload.phone),
        message=message,
        source=_clean(payload.source) or "footer",
    )
    db.add(item)
    db.flush()

    admins = list(db.scalars(select(User).where(User.role == UserRole.ADMIN.value, User.is_active.is_(True))).all())
    for admin in admins:
        notify_user(
            db,
            user=admin,
            type="support.message_created",
            title="Новое обращение в поддержку",
            body=f"{item.name} · {item.email}",
            payload={"support_message_id": str(item.id), "source": item.source},
        )

    log_event(
        db,
        event_type="support.message_created",
        entity_type="support_message",
        entity_id=item.id,
        message="Support message created from site footer",
        payload={"email": item.email, "source": item.source},
        request=request,
    )
    db.commit()
    db.refresh(item)
    return item
