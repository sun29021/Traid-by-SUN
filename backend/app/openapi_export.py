"""Write the OpenAPI schema to a file: `python -m app.openapi_export <path>`.

Used by scripts/gen-api-types.ps1 to generate the frontend's API types without
starting a server (AGENTS.md §4: frontend types come from OpenAPI).
"""

import json
import sys
import tempfile
from pathlib import Path

from app.core.config import Environment, Settings
from app.core.logging import close_log_handlers
from app.main import create_app


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.openapi_export <output.json>")
    with tempfile.TemporaryDirectory() as tmp:
        # A throwaway data dir: building the schema must not touch real data or logs.
        settings = Settings(_env_file=None, env=Environment.TEST, data_dir=Path(tmp))
        schema = create_app(settings, start_worker=False).openapi()
        close_log_handlers()
    Path(sys.argv[1]).write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
