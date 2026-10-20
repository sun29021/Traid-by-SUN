import pytest

from app.core.config import REPO_ROOT
from app.engine.detect import PaddleOcr
from app.engine.models import ModelRegistry


@pytest.fixture(scope="session")
def ocr() -> PaddleOcr:
    """Real PP-OCR on CPU (deterministic); skips when models are not installed."""
    registry = ModelRegistry.from_manifest(REPO_ROOT / "models", device="cpu")
    if not registry.ready:
        pytest.skip("OCR models not installed (run scripts/fetch_models.py)")
    return PaddleOcr(registry)
