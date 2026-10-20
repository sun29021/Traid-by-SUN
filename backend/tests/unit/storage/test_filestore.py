import pytest

from app.core.errors import StorageFailure
from app.db.models.enums import MimeType
from app.storage.filestore import FileStore, sanitize_original_name, sha256_hex


def test_write_is_content_addressed_and_idempotent(file_store: FileStore) -> None:
    data = b"hello traid"
    digest = sha256_hex(data)

    first = file_store.write(data, digest, MimeType.PNG)
    second = file_store.write(data, digest, MimeType.PNG)

    assert first == second == f"{digest[:2]}/{digest[2:4]}/{digest}.png"
    assert file_store.read_bytes(first) == data
    assert not list(file_store.root.rglob("*.tmp")) and len(list(file_store.root.rglob("*"))) == 3


@pytest.mark.parametrize(
    "path",
    [
        "../secrets.txt",
        "ab/cd/../../../x.png",
        "C:/Windows/win.ini",
        "/etc/passwd",
        "ab/cd/" + "0" * 64 + ".exe",
        "AB/CD/" + "A" * 64 + ".png",
    ],
)
def test_resolve_rejects_anything_but_storage_paths(file_store: FileStore, path: str) -> None:
    with pytest.raises(StorageFailure):
        file_store.resolve(path)


def test_missing_file_is_a_storage_error(file_store: FileStore) -> None:
    with pytest.raises(StorageFailure, match="missing"):
        file_store.read_bytes(f"ab/cd/{'ab' * 32}.png")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("token.jpg", "token.jpg"),
        (r"C:\Users\x\Desktop\scan 01.png", "scan 01.png"),
        ("../../etc/passwd", "passwd"),
        ("bad\x00name\x1f.png", "badname.png"),
        ("", None),
        (None, None),
        ("x" * 300, "x" * 255),
    ],
)
def test_sanitize_original_name(raw: str | None, expected: str | None) -> None:
    assert sanitize_original_name(raw) == expected
