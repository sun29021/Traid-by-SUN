"""Run the Traid server: `uv run python -m app` (from `backend/`).

Host and port come from settings, so the loopback-only rule always applies.
"""

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=not settings.is_production,
        reload_dirs=["app"] if not settings.is_production else None,
        log_config=None,
    )


if __name__ == "__main__":
    main()
