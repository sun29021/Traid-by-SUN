import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import REPO_ROOT
from app.engine.models import (
    ModelRegistry,
    ModelUnavailableError,
    available_devices,
    gpu_options,
    resolve_device,
)


def _write_manifest(model_dir: Path, file_bytes: bytes, sha: str | None = None) -> None:
    (model_dir / "tiny.onnx").write_bytes(file_bytes)
    manifest = {
        "schema": 1,
        "models": [
            {
                "name": "tiny",
                "role": "test",
                "version": "1",
                "file": "tiny.onnx",
                "sha256": sha or hashlib.sha256(file_bytes).hexdigest(),
                "license": "test",
                "required": True,
                "source": {},
            }
        ],
    }
    (model_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_missing_manifest_means_not_ready(tmp_path: Path) -> None:
    registry = ModelRegistry.from_manifest(tmp_path)

    assert registry.ready is False
    assert registry.status() == []


def test_checksum_is_verified_and_cached(tmp_path: Path) -> None:
    _write_manifest(tmp_path, b"model-bytes")
    registry = ModelRegistry.from_manifest(tmp_path)

    assert registry.checksum_ok("tiny") is True
    assert registry.ready is True

    (tmp_path / "tiny.onnx").write_bytes(b"tampered!!!!")  # different size → re-hashed
    assert registry.checksum_ok("tiny") is False
    assert registry.ready is False


def test_damaged_model_cannot_be_loaded(tmp_path: Path) -> None:
    _write_manifest(tmp_path, b"model-bytes", sha="0" * 64)
    registry = ModelRegistry.from_manifest(tmp_path)

    with pytest.raises(ModelUnavailableError, match="fetch_models"):
        registry.session("tiny")
    status = registry.status()[0]
    assert (status.present, status.checksum_ok, status.loaded) == (True, False, False)


def test_unknown_model_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(ModelUnavailableError):
        ModelRegistry.from_manifest(tmp_path).session("nope")


def test_device_resolution() -> None:
    assert "cpu" in available_devices()
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("auto") in available_devices()
    assert gpu_options("cpu", "auto") == {}
    assert gpu_options("directml", "auto") == {
        "performance_preference": "high_performance",
        "device_filter": "gpu",
    }
    assert gpu_options("directml", "1") == {"device_id": 1}


def test_real_models_load_on_cpu() -> None:
    registry = ModelRegistry.from_manifest(REPO_ROOT / "models", device="cpu")
    if not registry.ready:
        pytest.skip("OCR models not installed")

    session = registry.session("ppocr-rec")

    assert session.device == "cpu"
    assert "character" in session.metadata()
    assert registry.session("ppocr-rec") is session  # cached
    assert next(m for m in registry.status() if m.name == "ppocr-rec").loaded is True
