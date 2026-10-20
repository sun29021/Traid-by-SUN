from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.db.engine import Database, run_migrations
from app.main import create_app
from app.storage.filestore import FileStore
from tests.factories import make_user


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        env=Environment.TEST,
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "models",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # The worker thread is not started: tests run tasks synchronously via TaskRunner.run_once().
    with TestClient(create_app(settings, start_worker=False)) as test_client:
        yield test_client


@pytest.fixture
def db(settings: Settings) -> Iterator[Database]:
    database = Database.from_settings(settings)
    run_migrations(database.engine)
    yield database
    database.dispose()


@pytest.fixture
def owner_id(db: Database) -> str:
    return make_user(db, "owner")


@pytest.fixture
def file_store(settings: Settings) -> FileStore:
    return FileStore(settings.data_dir / "files")
