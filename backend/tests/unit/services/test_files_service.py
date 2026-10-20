from collections.abc import Callable

import pytest

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.engine import Database
from app.db.models.enums import FileKind
from app.repositories import files as files_repo
from app.services.files import StoredUpload, store_image_upload
from app.storage.filestore import FileStore
from tests.factories import image_bytes, make_user

Store = Callable[..., StoredUpload]


@pytest.fixture
def store(db: Database, file_store: FileStore, settings: Settings, owner_id: str) -> Store:
    def _store(data: bytes, kind: FileKind = FileKind.TARGET) -> StoredUpload:
        with db.session_factory() as session:
            return store_image_upload(
                session,
                file_store,
                settings,
                owner_id=owner_id,
                data=data,
                kind=kind,
                original_name=r"C:\photos\wall.png",
            )

    return _store


def test_stores_file_and_row(store: Store, file_store: FileStore) -> None:
    result = store(image_bytes("PNG"))

    assert result.created is True
    assert result.file.original_name == "wall.png"
    assert (result.file.width, result.file.mime_type) == (32, "image/png")
    assert file_store.resolve(result.file.storage_path).is_file()


def test_same_content_and_kind_is_deduplicated(store: Store) -> None:
    data = image_bytes("PNG")
    first = store(data)
    second = store(data)
    other_kind = store(data, FileKind.REFERENCE)

    assert second.created is False
    assert second.file.id == first.file.id
    assert other_kind.created is True
    assert other_kind.file.id != first.file.id
    assert other_kind.file.storage_path == first.file.storage_path  # bytes stored once


def test_files_are_owner_scoped(store: Store, db: Database, owner_id: str) -> None:
    stored = store(image_bytes("PNG")).file
    stranger = make_user(db, "stranger")

    with db.session_factory() as session:
        assert files_repo.get(session, owner_id, stored.id) is not None
        assert files_repo.get(session, stranger, stored.id) is None


def test_invalid_upload_stores_nothing(store: Store, file_store: FileStore) -> None:
    with pytest.raises(AppError) as caught:
        store(b"not an image at all")

    assert caught.value.code is ErrorCode.UNSUPPORTED_MEDIA_TYPE
    assert not file_store.root.exists() or not any(file_store.root.rglob("*.*"))
