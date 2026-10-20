"""Serving stored images to the owner (API.md §3.9).

Files are addressed by ID only; ownership is checked and the path always comes from the
content-addressed store. Content is immutable, so browsers may cache it for a year.
"""

import io
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from PIL import Image

from app.api.deps import AcceptedUserDep, SessionDep, allowed_query_params, get_file_store
from app.core.errors import NotFound
from app.repositories import files as files_repo
from app.storage.filestore import FileStore

router = APIRouter(prefix="/files", tags=["files"])

IMMUTABLE = "private, max-age=31536000, immutable"
FileStoreDep = Annotated[FileStore, Depends(get_file_store)]


@router.get(
    "/{file_id}",
    response_class=FileResponse,
    dependencies=[Depends(allowed_query_params("download"))],
)
def get_file(
    file_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    store: FileStoreDep,
    download: Annotated[bool, Query()] = False,
) -> FileResponse:
    stored = files_repo.get(session, user.id, file_id)
    if stored is None:
        raise NotFound("File not found")
    return FileResponse(
        store.resolve(stored.storage_path),
        media_type=stored.mime_type,
        filename=stored.original_name or f"{stored.kind}-{stored.id[:8]}",
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": IMMUTABLE},
    )


@router.get("/{file_id}/thumb", dependencies=[Depends(allowed_query_params("size"))])
def get_thumbnail(
    file_id: str,
    user: AcceptedUserDep,
    session: SessionDep,
    store: FileStoreDep,
    size: Annotated[Literal[256, 512], Query()] = 256,
) -> Response:
    """Downscaled preview (JPEG, or PNG when the image has transparency)."""
    stored = files_repo.get(session, user.id, file_id)
    if stored is None or not stored.mime_type.startswith("image/"):
        raise NotFound("File not found")
    with Image.open(store.resolve(stored.storage_path)) as image:
        image.thumbnail((size, size))
        has_alpha = image.mode in ("RGBA", "LA", "P")
        preview = image.convert("RGBA" if has_alpha else "RGB")
        buffer = io.BytesIO()
        if has_alpha:
            preview.save(buffer, format="PNG")
        else:
            preview.save(buffer, format="JPEG", quality=85)
    return Response(
        content=buffer.getvalue(),
        media_type="image/png" if has_alpha else "image/jpeg",
        headers={"Cache-Control": IMMUTABLE},
    )
