import pytest
from sqlalchemy import func, select

from app.db.engine import Database
from app.db.models import AuditEvent, User
from app.db.transaction import transaction


def _count(db: Database) -> int:
    with db.session_factory() as session:
        return session.scalar(select(func.count()).select_from(AuditEvent)) or 0


def _event() -> AuditEvent:
    return AuditEvent(action="settings.updated", details={})


def test_commits_when_no_transaction_is_open(db: Database) -> None:
    with db.session_factory() as session, transaction(session):
        session.add(_event())

    assert _count(db) == 1


def test_takes_over_and_commits_an_autobegun_transaction(db: Database) -> None:
    with db.session_factory() as session:
        session.scalar(select(User))  # read auto-begins a transaction
        with transaction(session):
            session.add(_event())

    assert _count(db) == 1


def test_nested_blocks_commit_once_and_roll_back_together(db: Database) -> None:
    with db.session_factory() as session, pytest.raises(RuntimeError), transaction(session):
        session.add(_event())
        with transaction(session):
            session.add(_event())
        raise RuntimeError("fail after inner block")

    assert _count(db) == 0


def test_joins_a_callers_explicit_transaction(db: Database) -> None:
    with db.session_factory() as session, pytest.raises(RuntimeError), session.begin():
        with transaction(session):
            session.add(_event())
        raise RuntimeError("caller rolls back")

    assert _count(db) == 0
