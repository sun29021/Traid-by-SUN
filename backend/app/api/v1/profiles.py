"""Style Profiles, their reference images and glyph review (API.md §3.3-3.5)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.deps import (
    AcceptedUserDep,
    SessionDep,
    SettingsDep,
    allowed_query_params,
    get_file_store,
    parse_csv_enum,
)
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.rate_limit import upload_limit
from app.db.models.enums import GlyphStatus, ReferenceStatus
from app.schemas.common import DataEnvelope, ListEnvelope, ListMeta
from app.schemas.profiles import (
    BulkResult,
    CoverageItem,
    GlyphBulk,
    GlyphOut,
    LearningOut,
    ProfileCreate,
    ProfileDelete,
    ProfileOut,
    ProfileUpdate,
    ReferenceOut,
    ReferenceUpload,
)
from app.services import glyphs as glyphs_service
from app.services import learning
from app.services import profiles as profiles_service
from app.services import references as references_service
from app.storage.filestore import FileStore

router = APIRouter(prefix="/profiles", tags=["profiles"])

FileStoreDep = Annotated[FileStore, Depends(get_file_store)]
MAX_GLYPH_PAGE = 200


@router.get(
    "",
    response_model=DataEnvelope[list[ProfileOut]],
    dependencies=[Depends(allowed_query_params("archived", "q"))],
)
def list_profiles(
    user: AcceptedUserDep,
    session: SessionDep,
    archived: Literal["false", "true", "all"] = "false",
    q: Annotated[str | None, Query(max_length=60)] = None,
) -> DataEnvelope[list[ProfileOut]]:
    """Most recently updated first. `archived=all` includes archived profiles."""
    archived_filter = {"false": False, "true": True, "all": None}[archived]
    return DataEnvelope(
        data=profiles_service.list_profiles(session, user.id, archived=archived_filter, query=q)
    )


@router.post("", response_model=DataEnvelope[ProfileOut], status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileCreate, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[ProfileOut]:
    return DataEnvelope(data=profiles_service.create_profile(session, user.id, body))


@router.get("/{profile_id}", response_model=DataEnvelope[ProfileOut])
def get_profile(
    profile_id: str, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[ProfileOut]:
    return DataEnvelope(data=profiles_service.get_profile(session, user.id, profile_id))


@router.patch("/{profile_id}", response_model=DataEnvelope[ProfileOut])
def update_profile(
    profile_id: str, body: ProfileUpdate, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[ProfileOut]:
    return DataEnvelope(data=profiles_service.update_profile(session, user.id, profile_id, body))


@router.post("/{profile_id}/archive", response_model=DataEnvelope[ProfileOut])
def archive_profile(
    profile_id: str, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[ProfileOut]:
    return DataEnvelope(data=profiles_service.set_archived(session, user.id, profile_id, True))


@router.post("/{profile_id}/unarchive", response_model=DataEnvelope[ProfileOut])
def unarchive_profile(
    profile_id: str, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[ProfileOut]:
    return DataEnvelope(data=profiles_service.set_archived(session, user.id, profile_id, False))


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: str, body: ProfileDelete, user: AcceptedUserDep, session: SessionDep
) -> Response:
    """Permanently delete an archived profile. `confirm_name` must equal its name."""
    profiles_service.delete_profile(session, user.id, profile_id, body.confirm_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{profile_id}/learning", response_model=DataEnvelope[LearningOut])
def get_learning(
    profile_id: str, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[LearningOut]:
    """Acceptance stats, learned starting adjustments and typical token position."""
    profile = profiles_service.get_owned(session, user.id, profile_id)
    return DataEnvelope(data=LearningOut.model_validate(learning.summary(session, profile)))


@router.get("/{profile_id}/coverage", response_model=DataEnvelope[list[CoverageItem]])
def get_coverage(
    profile_id: str, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[list[CoverageItem]]:
    return DataEnvelope(data=profiles_service.coverage(session, user.id, profile_id))


# ---------------------------------------------------------------- reference images


@router.post(
    "/{profile_id}/references",
    response_model=DataEnvelope[ReferenceUpload],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(upload_limit)],
)
def upload_references(
    profile_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    settings: SettingsDep,
    store: FileStoreDep,
    files: Annotated[list[UploadFile], File(description="1-50 JPEG, PNG or TIFF images")],
    known_text: Annotated[list[str] | None, Form(description="Optional, per file")] = None,
) -> DataEnvelope[ReferenceUpload]:
    """Store images, skip duplicates, report rejected files, queue glyph extraction."""
    limit = settings.max_upload_mb * 1024 * 1024 + 1  # one byte over → rejected as too large
    uploads = [
        references_service.UploadedFile(name=f.filename, data=f.file.read(limit)) for f in files
    ]
    result = references_service.upload(
        session,
        store,
        settings,
        owner_id=user.id,
        profile_id=profile_id,
        files=uploads,
        known_texts=known_text or [],
    )
    return DataEnvelope(data=result)


@router.get(
    "/{profile_id}/references",
    response_model=ListEnvelope[ReferenceOut],
    dependencies=[Depends(allowed_query_params("status", "cursor", "limit"))],
)
def list_references(
    profile_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> ListEnvelope[ReferenceOut]:
    items, next_cursor = references_service.list_references(
        session,
        user.id,
        profile_id,
        statuses=parse_csv_enum(status_filter, ReferenceStatus, "status"),
        cursor=cursor,
        limit=limit,
    )
    return ListEnvelope(data=items, meta=ListMeta(next_cursor=next_cursor, count=len(items)))


# ---------------------------------------------------------------- glyphs


@router.get(
    "/{profile_id}/glyphs",
    response_model=ListEnvelope[GlyphOut],
    dependencies=[
        Depends(allowed_query_params("char", "status", "min_quality", "cursor", "limit"))
    ],
)
def list_glyphs(
    profile_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    char: Annotated[str | None, Query(min_length=1, max_length=1)] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    min_quality: Annotated[float | None, Query(ge=0, le=1)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_GLYPH_PAGE)] = 100,
) -> ListEnvelope[GlyphOut]:
    """Grouped by character, best quality first."""
    items, next_cursor = glyphs_service.list_glyphs(
        session,
        user.id,
        profile_id,
        char=char,
        statuses=parse_csv_enum(status_filter, GlyphStatus, "status"),
        min_quality=min_quality,
        cursor=cursor,
        limit=limit,
    )
    return ListEnvelope(data=items, meta=ListMeta(next_cursor=next_cursor, count=len(items)))


@router.post("/{profile_id}/glyphs/bulk", response_model=DataEnvelope[BulkResult])
def bulk_update_glyphs(
    profile_id: str, body: GlyphBulk, user: AcceptedUserDep, session: SessionDep
) -> DataEnvelope[BulkResult]:
    updated = glyphs_service.bulk_update(session, user.id, profile_id, body)
    return DataEnvelope(data=BulkResult(updated=updated))
