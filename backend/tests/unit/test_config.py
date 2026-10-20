from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import REPO_ROOT, Settings


def test_defaults_are_local_and_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.data_dir == (REPO_ROOT / "data").resolve()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com"])  # noqa: S104
def test_non_loopback_host_is_refused(host: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, host=host)


def test_absolute_data_dir_is_kept(tmp_path: Path) -> None:
    assert Settings(_env_file=None, data_dir=tmp_path).data_dir == tmp_path
