"""Data access for `users`."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.models.enums import UserRole


def get(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def first_owner(session: Session) -> User | None:
    return session.scalar(
        select(User)
        .where(User.role == UserRole.OWNER.value)
        .order_by(User.created_at, User.id)
        .limit(1)
    )


def add(session: Session, user: User) -> User:
    session.add(user)
    session.flush()
    return user
