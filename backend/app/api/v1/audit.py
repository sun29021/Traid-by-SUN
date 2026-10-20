"""Read-only audit log (API.md §3.10)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps import AcceptedUserDep, SessionDep, allowed_query_params, parse_csv_enum
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.schemas.audit import AuditEventOut
from app.schemas.common import ListEnvelope, ListMeta
from app.services import audit
from app.services.audit import AuditAction

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "",
    response_model=ListEnvelope[AuditEventOut],
    dependencies=[Depends(allowed_query_params("action", "from", "to", "cursor", "limit"))],
)
def list_audit_events(
    _: AcceptedUserDep,
    session: SessionDep,
    action: Annotated[str | None, Query()] = None,
    created_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    created_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> ListEnvelope[AuditEventOut]:
    """Newest first. `from`/`to` are ISO-8601 timestamps with a timezone."""
    page = audit.list_events(
        session,
        actions=parse_csv_enum(action, AuditAction, "action"),
        created_from=created_from,
        created_to=created_to,
        cursor=cursor,
        limit=limit,
    )
    return ListEnvelope(
        data=[AuditEventOut.model_validate(event) for event in page.events],
        meta=ListMeta(next_cursor=page.next_cursor, count=len(page.events)),
    )
