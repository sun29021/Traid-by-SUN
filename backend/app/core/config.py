"""Application settings loaded from environment variables and `.env`.

All variables are documented in ARCHITECTURE.md §12 and `.env.example`.
Traid needs no secrets; every setting has a safe default.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRAID_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Environment.DEVELOPMENT
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    data_dir: Path = Path("./data")
    model_dir: Path = Path("./models")
    device: Literal["auto", "cpu", "directml", "cuda"] = "auto"
    # "auto" = DirectML high-performance GPU (the discrete GPU on hybrid laptops), or an index.
    gpu_device_id: str = Field(default="auto", pattern=r"^(auto|\d{1,2})$")
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    max_pixels: int = Field(default=40_000_000, ge=1_000_000, le=200_000_000)
    session_idle_hours: int = Field(default=12, ge=1, le=168)
    session_max_days: int = Field(default=7, ge=1, le=90)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        # Traid is a local, single-user app: it must never listen on a network interface.
        if value not in LOOPBACK_HOSTS:
            raise ValueError(
                f"TRAID_HOST must be a loopback address ({', '.join(sorted(LOOPBACK_HOSTS))})"
            )
        return value

    @field_validator("data_dir", "model_dir")
    @classmethod
    def _resolve_against_repo_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def frontend_dist_dir(self) -> Path:
        return REPO_ROOT / "frontend" / "dist"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
