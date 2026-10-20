"""The single local owner used while Traid runs without sign-in (ARCHITECTURE.md §7.1)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.db.models import User
from app.db.models.enums import UserRole
from app.db.transaction import transaction
from app.repositories import users as users_repo
from app.services import audit
from app.services.audit import AuditAction

LOCAL_OWNER_USERNAME = "owner"
LOCAL_OWNER_DISPLAY_NAME = "Xavier Sun"


def ensure_local_owner(session: Session) -> User:
    """Return the owner, creating it on first start. Safe to call on every startup."""
    with transaction(session):
        owner = users_repo.first_owner(session)
        if owner is not None:
            return owner
        return users_repo.add(
            session,
            User(
                username=LOCAL_OWNER_USERNAME,
                display_name=LOCAL_OWNER_DISPLAY_NAME,
                password_hash=None,
                role=UserRole.OWNER.value,
            ),
        )


def accept_aup(session: Session, user_id: str) -> User:
    """Record the Acceptable Use acknowledgement once (idempotent)."""
    with transaction(session):
        user = users_repo.get(session, user_id)
        if user is None:
            raise LookupError("Local owner is missing")
        if user.aup_accepted_at is None:
            user.aup_accepted_at = utcnow()
            audit.record(
                session, user_id=user.id, action=AuditAction.AUP_ACCEPTED, subject=("user", user.id)
            )
        return user
