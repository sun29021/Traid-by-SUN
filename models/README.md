# Models

ONNX model files used by the Traid engine are **downloaded, never committed**.
`manifest.json` lists each model's name, role, version, file, SHA-256, license and pinned source.
`scripts/fetch_models.py` downloads each source once, verifies the source's SHA-256, extracts the
model, verifies the model's SHA-256, and only then installs it here.

| Model | Role | Size | License |
|-------|------|------|---------|
| `ppocr_v4_det.onnx` | Text detection (PP-OCRv4 DB) | 4.7 MB | Apache-2.0 |
| `ppocr_v4_rec.onnx` | Text recognition (PP-OCRv4, CTC; dictionary embedded) | 10.9 MB | Apache-2.0 |
| `lama_inpaint_2025jan.onnx` | Text removal on structured backgrounds (LaMa, 512×512; CPU only) | 92.6 MB | Apache-2.0 |

Sources: PP-OCR from the `rapidocr-onnxruntime 1.4.4` wheel on PyPI (ONNX exports of PaddleOCR
models by RapidAI); LaMa from the OpenCV Zoo repository on Hugging Face (`opencv/inpainting_lama`),
pinned to a commit. LaMa is optional: without it Traid removes text with OpenCV Telea and reports
the fallback.
