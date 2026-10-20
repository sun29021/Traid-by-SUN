from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.engine import Database
from app.db.models import AuditEvent, Task, User
from tests.factories import make_user


def test_timestamps_are_stored_as_iso_utc_with_z(db: Database, owner_id: str) -> None:
    with db.session() as session:
        stored = session.execute(
            text("SELECT created_at FROM users WHERE id = :id"), {"id": owner_id}
        ).scalar_one()
        user = session.get(User, owner_id)

    assert stored.endswith("Z") and len(stored) == 24
    assert user is not None and user.created_at.tzinfo is not None


def test_non_utc_datetimes_are_converted_to_utc(db: Database, owner_id: str) -> None:
    plus_two = timezone(timedelta(hours=2))
    with db.session() as session:
        user = session.get(User, owner_id)
        assert user is not None
        user.locked_until = datetime(2026, 10, 20, 12, 0, tzinfo=plus_two)

    with db.session() as session:
        user = session.get(User, owner_id)
        assert user is not None
        assert user.locked_until == datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


def test_naive_datetimes_are_rejected(db: Database, owner_id: str) -> None:
    with pytest.raises(StatementError), db.session() as session:
        user = session.get(User, owner_id)
        assert user is not None
        user.locked_until = datetime(2026, 10, 20, 12, 0)


def test_check_constraints_reject_invalid_enum(db: Database) -> None:
    with pytest.raises(IntegrityError), db.session() as session:
        session.add(User(username="bad", display_name="Bad", password_hash="x", role="admin"))


def test_foreign_keys_are_enforced(db: Database) -> None:
    with pytest.raises(IntegrityError), db.session() as session:
        session.add(Task(owner_id="missing-user", type="detect", subject_type="system", payload={}))


def test_audit_events_are_append_only(db: Database, owner_id: str) -> None:
    with db.session() as session:
        event = AuditEvent(user_id=owner_id, action="auth.login", details={"ok": True})
        session.add(event)
        session.flush()
        event_id = event.id

    with pytest.raises(IntegrityError, match="append-only"), db.session() as session:
        session.execute(
            text("UPDATE audit_events SET action = 'x' WHERE id = :id"), {"id": event_id}
        )

    with pytest.raises(IntegrityError, match="append-only"), db.session() as session:
        session.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id})


def test_deleting_a_user_keeps_audit_rows_with_null_actor(db: Database) -> None:
    user_id = make_user(db, "temp")
    with db.session() as session:
        session.add(AuditEvent(user_id=user_id, action="auth.login", details={}))

    with db.session() as session:
        session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

    with db.session() as session:
        actors = session.execute(text("SELECT user_id FROM audit_events")).scalars().all()
    assert actors == [None]
