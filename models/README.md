# Models

ONNX model files used by the Traid engine are **downloaded, never committed**.
`manifest.json` (added in Phase 4) lists each model's name, version, source URL, SHA-256 and license.
`scripts/fetch_models.py` downloads and verifies them.
