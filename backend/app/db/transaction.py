"""Transaction helper so services own their transaction boundaries (ARCHITECTURE.md §6)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session, SessionTransactionOrigin

_OWNER_KEY = "traid.transaction_owner"


@contextmanager
def transaction(session: Session) -> Iterator[None]:
    """Run a unit of work atomically.

    - No transaction open: begin one, commit on success, roll back on error.
    - A transaction auto-begun by earlier reads on this session (e.g. loading the
      current user in a request): this unit of work takes it over and commits it.
    - Already inside a `transaction()` block, or inside a caller's explicit
      `session.begin()`: join it; the outermost owner commits or rolls back.
    """
    current = session.get_transaction()
    joined = session.info.get(_OWNER_KEY) or (
        current is not None and current.origin is not SessionTransactionOrigin.AUTOBEGIN
    )
    if joined:
        yield
        return

    session.info[_OWNER_KEY] = True
    try:
        if current is None:
            with session.begin():
                yield
        else:
            try:
                yield
            except BaseException:
                session.rollback()
                raise
            session.commit()
    finally:
        session.info.pop(_OWNER_KEY, None)
