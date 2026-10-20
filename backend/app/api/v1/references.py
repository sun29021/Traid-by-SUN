"""Single reference images and glyphs, addressed by their own ID (API.md §3.4-3.5)."""

from fastapi import APIRouter, Response, status

from app.api.deps import AcceptedUserDep, SessionDep
from app.schemas.common import ApiModel, DataEnvelope
from app.schemas.profiles import GlyphOut, GlyphUpdate, ReferenceOut, ReferenceUpdate
from app.schemas.tasks import TaskOut
from app.services import glyphs as glyphs_service
from app.services import references as references_service

router = APIRouter(tags=["profiles"])


class ReferenceChange(ApiModel):
    reference: ReferenceOut
    task: TaskOut | None


@router.patch("/references/{reference_id}", response_model=DataEnvelope[ReferenceChange])
def update_reference(
    reference_id: str, body: ReferenceUpdate, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[ReferenceChange]:
    """Set the known text. A processed image is re-extracted with it (task returned)."""
    reference, task = references_service.set_known_text(
        session, user.id, reference_id, body.known_text
    )
    return DataEnvelope(
        data=ReferenceChange(
            reference=reference, task=TaskOut.model_validate(task) if task else None
        )
    )


@router.post(
    "/references/{reference_id}/reextract",
    response_model=DataEnvelope[TaskOut],
    status_code=status.HTTP_202_ACCEPTED,
)
def reextract_reference(
    reference_id: str, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[TaskOut]:
    """Replace this image's unreviewed glyphs; confirmed/rejected decisions are kept."""
    task = references_service.reextract(session, user.id, reference_id)
    return DataEnvelope(data=TaskOut.model_validate(task))


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(reference_id: str, user: AcceptedUserDep, session: SessionDep) -> Response:
    """Remove the image and every glyph extracted from it."""
    references_service.delete_reference(session, user.id, reference_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/glyphs/{glyph_id}", response_model=DataEnvelope[GlyphOut])
def update_glyph(
    glyph_id: str, body: GlyphUpdate, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[GlyphOut]:
    return DataEnvelope(data=glyphs_service.update_glyph(session, user.id, glyph_id, body))
