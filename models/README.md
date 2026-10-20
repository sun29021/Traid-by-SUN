# Models

ONNX model files used by the Traid engine are **downloaded, never committed**.
`manifest.json` lists each model's name, role, version, file, SHA-256, license and pinned source.
`scripts/fetch_models.py` downloads each source once, verifies the source's SHA-256, extracts the
model, verifies the model's SHA-256, and only then installs it here.

| Model | Role | Size | License |
|-------|------|------|---------|
| `ppocr_v4_det.onnx` | Text detection (PP-OCRv4 DB) | 4.7 MB | Apache-2.0 |
| `ppocr_v4_rec.onnx` | Text recognition (PP-OCRv4, CTC; dictionary embedded) | 10.9 MB | Apache-2.0 |

Source: the `rapidocr-onnxruntime 1.4.4` wheel on PyPI (ONNX exports of PaddleOCR models by RapidAI).
The text-removal model (LaMa) is added in Phase 7.
