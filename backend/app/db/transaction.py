"""Transaction helper so services own their transaction boundaries (ARCHITECTURE.md §6)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def transaction(session: Session) -> Iterator[None]:
    """Run a unit of work atomically.

    Starts and commits a transaction when none is open. When the caller already opened
    one (e.g. a service calling another service), the work joins it and the outermost
    owner commits or rolls back.
    """
    if session.in_transaction():
        yield
        return
    with session.begin():
        yield
