# Traid

**Style-matched token text replacement.** Designed & developed by **Xavier Sun**.

Traid replaces a short printed token in a photo or scan with a new value so that the new characters match the real print. It reuses real glyphs from your own reference images and adapts them to each target image. Everything runs locally; images never leave your machine.

> Status: **Phases 0–4 done** (foundation, database and worker, local-mode security, design system and Welcome screen, text detection engine). Product features are built phase by phase (see `IMPLEMENTATION_PLAN.md`).

## Project documents (source of truth)

| File | What it defines |
|------|-----------------|
| [PRD.md](PRD.md) | Product scope, user stories, requirements, approved decisions |
| [DESIGN.md](DESIGN.md) | Visual design system and UX rules |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Stack, layers, folders, security, testing, deployment |
| [DATABASE.md](DATABASE.md) | Data model |
| [API.md](API.md) | HTTP API contract |
| [AGENTS.md](AGENTS.md) | Rules for anyone (human or AI) changing the code |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Ordered phases and tasks |

## Prerequisites (Windows 10/11)

- **Python** (any recent version) with **uv**: `python -m pip install --user uv`. uv installs the project's own Python 3.11.
- **Node.js** 20.19 or newer (LTS).
- **Git**.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This creates `backend\.venv` (Python 3.11), installs `frontend\node_modules`, and downloads the AI models (about 15 MB, checksum-verified) into `models\`. To fetch models again later: `backend\.venv\Scripts\python.exe -I scripts\fetch_models.py`. Copy `.env.example` to `.env` only if you want to change defaults. Traid needs no API keys or secrets.

## Develop

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

- UI: http://localhost:5173 (Vite, proxies `/api` to the backend)
- API: http://127.0.0.1:8765/api/v1/health
- API docs (development only): http://127.0.0.1:8765/api/docs

## Quality checks

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check.ps1
```

Runs ruff, ruff format, mypy (strict), pytest, the API-types freshness check, ESLint, Prettier, TypeScript and Vitest. Every change must pass this before it is considered done.

End-to-end browser tests (production build + real backend on port 8766 with a throwaway data folder; uses your installed Google Chrome):

```powershell
cd frontend; npm run e2e
```

After changing any backend endpoint or schema, regenerate the frontend API types and commit the result:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\gen-api-types.ps1
```

## Run the production build locally

```powershell
cd frontend; npm run build; cd ..\backend
$env:TRAID_ENV = 'production'; .\.venv\Scripts\python.exe -m app
```

Then open http://127.0.0.1:8765. The backend serves the built UI and the API from one process, bound to `127.0.0.1` only.

## Repository layout

```
backend/    FastAPI app (api → services → repositories/storage/worker; engine is a pure image library)
frontend/   React + TypeScript SPA (design tokens in src/styles/tokens.css)
scripts/    setup, dev and check scripts (PowerShell)
models/     ONNX model manifest (model files are downloaded, never committed)
data/       runtime data: database, images, backups, logs (git-ignored)
```

## Data and privacy

All data lives in `data/` (configurable with `TRAID_DATA_DIR`). It is git-ignored. Enabling Windows BitLocker on the drive that holds it is recommended.

## Acceptable use

Only use Traid on documents and images you own or are authorized to produce and edit. Do not use it to alter identity documents, currency, financial instruments, official certificates or other people's documents.

---

© Xavier Sun. Traid · Designed & developed by Xavier Sun.
