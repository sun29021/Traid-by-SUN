"""Shared helpers for API tests that need images with known text."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.http_security import CLIENT_HEADER, CLIENT_HEADER_VALUE
from app.engine.types import Region, RGBImage
from app.main import create_app
from app.worker.runner import TaskRunner
from tests.factories import png_bytes
from tests.fixtures.generate import Surface, TokenFixture, make_token_image


@dataclass
class FixtureDetector:
    """Answers with the true text box of known fixture images (no model files needed)."""

    regions: dict[bytes, list[Region]] = field(default_factory=dict)
    fail: bool = False

    def register(self, fixture: TokenFixture) -> None:
        region = Region(quad=fixture.quad, text=fixture.text, confidence=0.99)
        self.regions[fixture.image.tobytes()] = [region]

    def detect(self, image: RGBImage) -> list[Region]:
        if self.fail:
            raise RuntimeError("detector exploded")
        return list(self.regions.get(np.ascontiguousarray(image).tobytes(), []))


@dataclass
class Studio:
    """An accepted API client plus synchronous control over the worker."""

    client: TestClient
    detector: FixtureDetector

    @property
    def runner(self) -> TaskRunner:
        runner: TaskRunner = self.client.app.state.task_runner  # type: ignore[attr-defined]
        return runner

    def run_tasks(self) -> None:
        while self.runner.run_once():
            pass

    def token_png(self, text: str, surface: Surface = "print", seed: int = 0) -> bytes:
        fixture = make_token_image(text, surface, seed=seed)
        self.detector.register(fixture)
        return png_bytes(fixture.image)

    def create_profile(self, **fields: Any) -> dict[str, Any]:
        body = {"name": "Receipt Token A", "surface_type": "print", **fields}
        response = self.client.post("/api/v1/profiles", json=body)
        assert response.status_code == 201, response.text
        data: dict[str, Any] = response.json()["data"]
        return data

    def upload(self, profile_id: str, *files: tuple[str, bytes], **form: Any) -> Any:
        return self.client.post(
            f"/api/v1/profiles/{profile_id}/references",
            files=[("files", (name, data, "image/png")) for name, data in files],
            data=form,
        )


@pytest.fixture
def studio(settings: Settings) -> Iterator[Studio]:
    detector = FixtureDetector()
    app = create_app(settings, start_worker=False, detector=detector)
    with TestClient(app, headers={CLIENT_HEADER: CLIENT_HEADER_VALUE}) as client:
        client.post("/api/v1/system/welcome", json={"accept_aup": True})
        yield Studio(client, detector)
