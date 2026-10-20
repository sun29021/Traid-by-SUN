# ARCHITECTURE — Traid

**Owner:** Xavier Sun
**Status:** Draft v1.0
**Derives from:** PRD.md, DESIGN.md
**Principle:** the simplest reliable architecture for a single-user, local, image-processing application. One process, one database file, one folder of files. No microservices, no message brokers, no cloud.

---

## 1. Architecture at a glance

```
 Browser (localhost)                         Traid server process (Python)
┌──────────────────────┐   HTTP/JSON    ┌──────────────────────────────────────────────┐
│ React SPA            │ ─────────────▶ │ FastAPI app  (/api/v1/*, static SPA files)   │
│  pages / features    │ ◀───────────── │   ├─ api (routers, auth deps, schemas)       │
│  TanStack Query      │  cookie auth   │   ├─ services (business rules, ownership)    │
│  canvas + SVG overlay│                │   ├─ repositories (SQLAlchemy)  ─▶ SQLite    │
└──────────────────────┘                │   ├─ storage (content-addressed files) ─▶ FS │
                                        │   ├─ worker (1 thread, persisted task queue) │
                                        │   └─ engine (pure image pipeline)            │
                                        │        └─ ONNX Runtime: PP-OCR, LaMa         │
                                        └──────────────────────────────────────────────┘
```

- **Single deployable:** in production mode the FastAPI process serves both the API and the built SPA from `127.0.0.1:8765`.
- **Single worker thread** executes heavy engine work (detection, extraction, render, batch) in order. This avoids GPU/CPU contention and keeps memory predictable. API requests stay responsive because they never run engine code inline.
- **Engine is a pure library.** `engine/` takes NumPy arrays and dataclasses in, returns arrays and dataclasses out. It knows nothing about HTTP, DB or files. This makes it testable with fixture images and swappable (Phase 2 generative engine).

---

## 2. Tech stack (with reasoning)

### 2.1 Backend
| Choice | Version | Why |
|--------|---------|-----|
| **Python** | 3.11 | Best ecosystem for image processing and ML inference. |
| **FastAPI** + **Uvicorn** | latest stable | Typed request/response models, automatic OpenAPI, simple dependency injection for auth. |
| **Pydantic v2** | latest stable | Validation and settings (`pydantic-settings`). |
| **SQLAlchemy 2.x** + **Alembic** | latest stable | Typed ORM, migrations; lets us move to Postgres later without rewriting queries. |
| **SQLite** (WAL mode) | bundled | Zero-ops, single file, perfect for single user; transactional. |
| **NumPy**, **OpenCV** (`opencv-python-headless`), **Pillow** | latest stable | Geometry, binarization, morphology, classical inpainting, Poisson blending, image IO incl. ICC/DPI. |
| **ONNX Runtime** (`onnxruntime` CPU; optional `onnxruntime-directml` on Windows GPU or `onnxruntime-gpu` for CUDA) | latest stable | One inference runtime for all models, no PyTorch needed in MVP, works on any Windows GPU via DirectML. |
| **RapidOCR** (`rapidocr-onnxruntime`) | latest stable | Ships PP-OCR detection/recognition pipelines on ONNX Runtime; easy Windows install; can return per-character positions. |
| **LaMa (big-lama) ONNX export** | pinned file | State-of-the-art free inpainting for removing text while keeping paper texture. |
| **argon2-cffi** | latest stable | Password hashing (Argon2id). |
| **uv** | latest stable | Fast, reproducible Python env + lock file. |
| **pytest**, **httpx** | latest stable | Tests. |
| **ruff**, **mypy** | latest stable | Lint/format, type checking. |

Not used on purpose: Celery/Redis (single worker thread is enough), PyTorch (not needed until Phase 2), Docker as a requirement (optional only), any cloud SDK.

### 2.2 Frontend
| Choice | Why |
|--------|-----|
| **React 18 + TypeScript (strict)** | Mature, typed, large component ecosystem. TypeScript is pinned to 5.x: tools such as `openapi-typescript` do not support TypeScript 6 yet (decision 2026-10-20). |
| **Vite** | Fast dev server and build; proxy to backend in dev. |
| **React Router** | Simple URL-driven routing (tabs and filters live in the URL). |
| **TanStack Query** | Server state, caching, polling of tasks, retries. |
| **CSS Modules + CSS custom properties** | Implements DESIGN.md tokens directly; no utility-class sprawl; no runtime CSS-in-JS. |
| **Zod** | Client-side form validation that mirrors API rules. |
| **lucide-react** | The single icon set required by DESIGN.md. |
| **@fontsource/ibm-plex-sans, @fontsource/ibm-plex-mono** | Bundled fonts for offline use. |
| **Vitest + Testing Library**, **Playwright** (+ `@axe-core/playwright`) | Unit/component tests and E2E with accessibility scans. E2E uses the installed Google Chrome (`channel: chrome`) so no browser download is required. |
| **openapi-typescript** (dev) | Generates `src/lib/api/schema.d.ts` from the backend's OpenAPI schema (`scripts/gen-api-types.ps1`); `scripts/check.ps1` fails when it is stale. |
| **ESLint + Prettier** | Lint/format. |

Canvas: native HTML Canvas 2D for the image + an SVG overlay layer in image coordinates for regions and handles. No canvas framework needed.

No global state library: server state in TanStack Query, editor session state in a single `useReducer` store inside the Editor feature (supports undo/redo).

---

## 3. Backend architecture

### 3.1 Layers and rules

| Layer | Responsibility | May call |
|-------|---------------|----------|
| `api/` routers | HTTP only: parse/validate (Pydantic schemas), auth dependencies, map results to responses | services |
| `services/` | Business rules, ownership checks, transactions, enqueueing tasks, audit writes | repositories, storage, worker (enqueue), engine (only via worker handlers) |
| `repositories/` | All SQL via SQLAlchemy; every query scoped by `owner_id` | db |
| `storage/` | Save/read files by content hash; thumbnails; path safety | filesystem |
| `worker/` | Persisted task queue, single thread, task handlers | services, engine, storage |
| `engine/` | Pure image pipeline | numpy/opencv/onnxruntime only |
| `core/` | Config, logging, errors, security helpers | — |

Dependency direction is strictly downward. `engine` never imports from other app packages.

### 3.2 Engine modules

```
engine/
  types.py          Quad, Region, CharBox, GlyphSample, RenderParams, QualityReport, …
  io.py             decode/encode with ICC/DPI preservation, JPEG quality estimate
  models.py         lazy ONNX session loader + device selection + checksum check
  detect.py         text detection & recognition (RapidOCR) → Regions
  candidates.py     token candidate scoring (pattern, position prior, style similarity)
  geometry.py       homography rectify / inverse warp
  segment.py        per-character boxes, baseline, cap height, pitch
  matte.py          background/ink estimate → soft alpha glyph masks
  inpaint.py        removal mask + LaMa (fallback OpenCV Telea)
  glyph_select.py   choose glyph per character (same-image first, then bank)
  layout.py         slot reuse or alignment/spacing layout
  harmonize.py      illumination transfer, ink colour, blur match, grain match
  composite.py      alpha composite with feather, mask enforcement
  verify.py         OCR read-back, seam score, statistics → QualityReport
  pipeline.py       orchestrates stages; exposes Synthesizer interface
```

**Synthesizer interface** (FR-E14): `render(context, new_text, params) -> RenderResult`. MVP implementation: `GlyphTransplantSynthesizer`. Phase 2 adds `GenerativeSynthesizer` behind the same interface, selected per profile.

### 3.3 Caching for fast re-renders
Per edit job the worker persists intermediate artefacts on first render: rectified crop, character boxes, removal mask, inpainted background (as files referenced in job `artifacts`). Re-renders after an adjustment reuse them and only redo layout → harmonize → composite → verify (target ≤ 3 s on CPU). Cache is invalidated when the region quad changes.

Batch items with the same template share the template's inpainted background and geometry, so each item only runs layout → harmonize → composite → verify.

### 3.4 Task worker
- `tasks` table is the queue (DATABASE.md). Enqueue = insert row `queued`.
- One daemon thread polls with a 250 ms idle sleep, claims the oldest `queued` task inside a transaction, runs its handler, writes progress (`progress`, `message`) at stage boundaries, sets `succeeded` / `failed`.
- Cancellation: `cancel_requested` flag checked between stages and between batch items.
- On startup: any `running` task → `failed` with `TASK_INTERRUPTED` (owner can retry).
- Handlers: `extract_glyphs`, `detect`, `render`, `batch_run`, `batch_export`, `backup`.
- ONNX sessions are loaded once (lazily) and kept in the worker for the process lifetime.

---

## 4. Frontend architecture

```
frontend/src/
  app/            router.tsx, providers.tsx (QueryClient, Auth), AppShell
  styles/         tokens.css (DESIGN.md tokens), reset.css, fonts.css
  components/     design-system primitives (Button, Input, TokenInput, Slider,
                  Select, Dialog, Drawer, Toast, Table, Tabs, Badge, Skeleton,
                  DropZone, Banner, MetricRow, ProgressBar, Tooltip, EmptyState)
  features/
    auth/         SetupPage, SignInPage, useSession, RequireAuth
    home/         HomePage
    profiles/     ProfilesPage, ProfileDetail (tabs), GlyphGrid, CoverageMatrix
    editor/       EditorPage, Canvas/, Overlay/, Inspector/, editorStore (reducer + undo)
    batch/        BatchPage, steps, ReviewDrawer
    history/      HistoryPage, JobDetailPage
    settings/     SettingsPage + sections, AuditLog, About
    tasks/        TasksChip, useTask (polling)
  lib/
    api/          client.ts (fetch wrapper, CSRF header, error mapping), endpoints per resource, types
    hooks/        useHotkeys, useDebounce, useUrlState
    format/       numbers, dates, file sizes
  main.tsx
```

Rules:
- Pages compose feature components; features compose `components/` primitives. Primitives never import features.
- All server calls go through `lib/api`. No `fetch` elsewhere.
- Task progress: `useTask(taskId)` polls `GET /tasks/{id}` every 500 ms while `queued|running`, then invalidates the affected queries.
- Images are loaded from `GET /files/{id}` (authenticated by cookie); the canvas uses `ImageBitmap` and draws at device pixel ratio; at ≥ 100% zoom uses nearest-neighbour (`imageSmoothingEnabled = false`) so pixels can be judged.
- Editor state (region quad, new text, params, undo stack) lives in `editorStore`; persisted to the server only on Generate/Accept.

---

## 5. Data flow

### 5.1 Profile training
```
Upload refs ─▶ POST /profiles/{id}/references (multipart)
   storage.save (sha256 dedupe) ─▶ files + reference_images rows (status=pending)
   enqueue extract_glyphs task ─▶ worker:
      decode ─▶ detect ─▶ for each region matching charset: rectify ─▶ segment ─▶ matte
      ─▶ save glyph RGBA PNGs ─▶ glyph rows (status=auto, metrics, quality)
      ─▶ reference status=processed (or failed + error_code)
   UI polls task ─▶ Glyph review ─▶ PATCH glyphs (confirm/relabel/reject)
   coverage recomputed on read ─▶ profile status Ready when rule satisfied
```

### 5.2 Single edit
```
Drop image ─▶ POST /jobs (file + profile_id) ─▶ job(status=uploaded) + detect task
worker detect ─▶ regions + candidate scores saved on job ─▶ status=detected
UI shows regions; owner confirms/adjusts ─▶ PUT /jobs/{id}/region
Owner types token ─▶ POST /jobs/{id}/render {new_text, params} ─▶ render task
worker render ─▶ (cached?) rectify/segment/matte/inpaint ─▶ glyph_select ─▶ layout
             ─▶ harmonize ─▶ composite ─▶ verify ─▶ result file + quality ─▶ status=rendered
UI cross-fades result; adjustments ─▶ POST /render again (cache reused)
Accept ─▶ POST /jobs/{id}/accept ─▶ learning update (glyph counters, learned params,
          typical region) + audit ─▶ status=accepted
Export ─▶ GET /jobs/{id}/export ─▶ encoded file (format/DPI/ICC preserved, marker) + audit
```

### 5.3 Learning update (inside accept transaction)
1. `edit_job_glyphs` rows for the accepted render → `glyphs.accept_count += 1`.
2. Profile `learned_params`: exponential moving average (α = 0.2) of the owner's non-default adjustments on accepted jobs; used as starting params for the next render.
3. Profile `typical_region`: running mean/variance of the normalized token bbox (position relative to image size) for candidate scoring.
4. Rejects → `glyphs.reject_count += 1` for glyphs used in the rejected render.
5. Glyph ranking score used in selection = condition similarity × (1 + accept_count) / (1 + accept_count + 2 × reject_count).

---

## 6. Database interaction

- SQLAlchemy 2.0 ORM, synchronous sessions (SQLite + single worker; simpler than async and fast enough).
- One `Session` per request via FastAPI dependency; services own transaction boundaries with `app.db.transaction.transaction(session)`: it begins and commits when no transaction is open, takes over and commits a transaction that earlier reads auto-began (e.g. loading the current user), and joins an enclosing `transaction()` block or a caller's explicit `session.begin()` (so a service can call another service atomically).
- Timestamps use the `UtcDateTime` column type (ISO-8601 UTC with `Z`, naive datetimes rejected); JSON columns use `JsonText` + a `json_valid` CHECK. Enum CHECK constraints are generated from the Python enums (`check_in`), and a test compares ORM models against migrations so they cannot drift.
- Worker uses its own session per task stage; progress updates commit independently of task results.
- SQLite pragmas on connect: `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL`.
- All repository functions take `owner_id` and include it in `WHERE` clauses (ownership by construction).
- Migrations: Alembic, run automatically on startup **after** an automatic pre-migration backup (DATABASE.md §9).
- Large binary data is never stored in the DB — only file references.

---

## 7. Authentication & authorization

### 7.1 MVP: local mode, no sign-in (PRD D-03, changed 2026-10-20)

- **Model:** exactly one `owner` user, created automatically at startup if the `users` table is empty (username `owner`, display name "Xavier Sun", no password). Every request acts as this user via the `current_user` dependency, so services and repositories keep their `owner_id` scoping unchanged.
- **Local request guard** (replaces sessions/CSRF while there is no login). Because any website open in the browser can send requests to `127.0.0.1`, the API accepts a request only if:
  1. the Host header is local (already enforced, DNS-rebinding protection);
  2. the `Origin` header, when present, is Traid's own origin (`http://127.0.0.1:8765`, `http://localhost:8765`, and `http://localhost:5173` in development);
  3. every state-changing request (`POST/PUT/PATCH/DELETE`) carries the header `X-Traid-Client: web`. Browsers only let other sites send custom headers after a CORS preflight, which Traid never approves, so form posts and `fetch` calls from other origins fail with `403 CSRF_FAILED`.
  Reads of images are protected by `Cross-Origin-Resource-Policy: same-origin` (already set) and the absence of CORS headers for other origins.
- **Acceptable Use:** acknowledged once on the Welcome screen; stored as `users.aup_accepted_at`. Until acknowledged, engine endpoints return `403 FORBIDDEN` with `details.reason = "aup_required"`.
- **Not protected against:** other programs running as the same Windows user (they could read `data/` directly anyway). Recommendation for shared PCs: a separate Windows account + BitLocker.

### 7.2 Later: optional password lock (US-02, not in MVP)

When enabled, the design below applies on top of 7.1 without changing data ownership:
- **Passwords:** Argon2id (argon2-cffi defaults, time_cost ≥ 3, memory ≥ 64 MiB). Length 10–128; no composition rules; reject the username as password.
- **Sessions:** opaque 32-byte random token in cookie `traid_session` (`HttpOnly`, `SameSite=Strict`, `Path=/`). Only the SHA-256 is stored. Idle timeout 12 h (sliding), absolute 7 days. Logout revokes the row.
- **CSRF:** `X-Traid-CSRF` synchronizer token from `GET /auth/me` replaces the static `X-Traid-Client` header.
- **Brute force:** 5 failed logins → 5-minute lock; per-IP limiter on `/auth/login`.
- **Authorization:** `current_user` resolves from the session; `require_role("owner")` guards owner-only endpoints; foreign resources return **404**. The `sessions` table already exists for this.

---

## 8. API architecture

- REST over JSON, prefix `/api/v1`. Full contract in API.md.
- Uniform envelopes: success `{ "data": … , "meta"?: … }`; error `{ "error": { "code", "message", "details"?, "request_id" } }`.
- Long-running work returns `202 Accepted` with a task object; clients poll `/tasks/{id}`.
- Files: upload via `multipart/form-data`; download via `/files/{id}` with correct `Content-Type`, `Cache-Control: private, max-age=31536000, immutable` (content-addressed), `X-Content-Type-Options: nosniff`.
- Cursor pagination for lists.
- OpenAPI generated by FastAPI; frontend types generated from it (`openapi-typescript`, dev dependency) to keep contracts in sync.

---

## 9. External services

| Service | When | Notes |
|---------|------|-------|
| Model files (PP-OCR det/rec ONNX, LaMa ONNX) | Setup only, via `scripts/fetch-models` | Pinned URLs + SHA-256 in `models/manifest.json`; download fails closed on checksum mismatch. Owner can also copy files manually. |
| Anything else at runtime | Never | No telemetry, no analytics, no cloud AI APIs, no update checks. |

---

## 10. AI architecture

### 10.1 MVP: Glyph Transplant engine
| Stage | Technique | Model? |
|-------|-----------|--------|
| Detect & read | PP-OCR detection (DB) + recognition (SVTR/CRNN) via RapidOCR | ✅ ONNX |
| Choose token | Weighted score: regex match, Gaussian position prior from `typical_region`, glyph-style similarity, OCR confidence | Rule-based + learned stats |
| Rectify | Homography from quad (OpenCV) | — |
| Segment characters | Sauvola/Otsu binarization, connected components, merge/split guided by OCR char count and CTC positions | — |
| Soft mask | **Ink mode:** background estimate (inpainted) + ink colour estimate → alpha = clip((bg − I)/(bg − ink)) per channel-luminance. **Relief mode:** binary glyph mask from segmentation, dilated to include the stroke's highlight/shadow rim; the RGB patch itself is kept as the glyph texture. | — |
| Remove | Dilated union of glyph alphas → LaMa inpainting; OpenCV Telea fallback | ✅ ONNX |
| Select glyphs | Same-image glyphs first; else bank glyphs ranked by condition similarity (cap height, stroke width, blur σ, background luminance, contrast, angle) × learned acceptance score | Learned stats |
| Layout | Slot reuse for equal length; else alignment + pitch/advances from profile | — |
| Harmonize | Scale to cap height; **ink mode:** ink colour transfer + shading ratio from local background; **relief mode:** low-frequency illumination of the patch replaced by the target's local illumination (high-frequency material detail kept). Both: Gaussian blur to match estimated σ; additive grain matched to measured noise σ; inverse warp | — |
| Composite | **Ink mode:** alpha composite, 2–4 px feather. **Relief mode:** gradient-domain (Poisson) blending via OpenCV `seamlessClone` (mixed gradients) inside the mask. Both: hard mask enforcement | — |

The mode comes from the profile's `surface_type` (PRD FR-E15): `print`, `paint` → ink; `laser_mark`, `engraved` → relief. For relief profiles, glyph selection adds a lighting-direction term (dominant gradient angle of the stroke rim, stored per glyph) with double weight, because highlights/shadows on engraved strokes only look right when the light comes from the same side.
| Encode | Same format; JPEG at estimated source quality | — |
| Verify | OCR read-back (same OCR model), seam gradient score, inside/outside statistics | ✅ ONNX |

Determinism: all random operations (grain) use a seed stored on the job.

### 10.2 "Learning" in MVP (honest definition)
Traid learns by **curating and ranking real data** and **adapting defaults** — no neural-network training in MVP:
- Glyph bank grows from references and confirmed real characters from targets.
- Per-glyph acceptance statistics change which samples are chosen.
- Learned default adjustments and typical token position per profile.

### 10.3 Phase 2 (future, not MVP): Generative engine
- Build a paired synthetic dataset from the glyph bank (render random tokens onto real backgrounds with the MVP engine) + real references.
- Fine-tune an open scene-text-editing diffusion model (LoRA) on GPU with PyTorch in a separate `training/` package (not loaded by the app).
- Export to ONNX and plug in as `GenerativeSynthesizer`; MVP verify stage stays as the gatekeeper.
- Requires: CUDA GPU ≥ 12 GB VRAM, owner approval, separate dependency group.
- **Owner hardware note:** the RTX 3050 Laptop GPU has 4 GB VRAM — enough for MVP inference, **not** enough to fine-tune a diffusion model locally. Phase 2 would need a rented cloud GPU for training (inference could then run locally only for a small exported model). Decision deferred until Phase 2 is proposed.

### 10.4 Model management
- `models/manifest.json`: name, version, file, sha256, license, source URL.
- `engine/models.py` verifies checksum at first load, picks device: `TRAID_DEVICE=auto` → DirectML/CUDA if available, else CPU; records device in `/system/status`.
- **Owner hardware (PRD D-09):** dual-GPU laptop (NVIDIA RTX 3050 Laptop 4 GB + AMD Radeon integrated). Use **`onnxruntime-directml`** (no CUDA toolkit/cuDNN install needed). DirectML adapter numbering does not always match Task Manager, so `TRAID_GPU_DEVICE_ID=auto` picks the adapter with the most dedicated video memory (the NVIDIA GPU); an explicit index overrides it. Settings → Engine shows the chosen adapter's name. Added in Phase 4 (task 4.3).
- VRAM budget (4 GB): LaMa runs on a crop around the token (≤ 1024 px side) and OCR on a downscaled copy for detection, so peak VRAM stays well under 2 GB. If a GPU run fails with out-of-memory, the stage retries once on CPU and reports it in the quality report.
- Performance targets are measured on AC power; on battery Windows throttles the dGPU and Traid may pick the integrated GPU.

---

## 11. Folder structure

```
Traid by SUN/
├─ AGENTS.md  PRD.md  DESIGN.md  ARCHITECTURE.md  DATABASE.md  API.md  IMPLEMENTATION_PLAN.md
├─ README.md                      setup & run instructions
├─ .env.example                   documented variables, no secrets
├─ .gitignore                     data/, models/*.onnx, .env, node_modules, .venv, dist
├─ backend/
│  ├─ pyproject.toml  uv.lock  alembic.ini
│  ├─ app/
│  │  ├─ main.py                  app factory, static SPA mount, startup hooks
│  │  ├─ core/                    config.py, logging.py, errors.py, security.py, rate_limit.py
│  │  ├─ db/                      engine.py (session, pragmas), base.py, models/*.py
│  │  ├─ migrations/              Alembic env + versions/
│  │  ├─ repositories/            users.py, sessions.py, profiles.py, references.py, glyphs.py,
│  │  │                           jobs.py, batches.py, tasks.py, audit.py, files.py, settings.py
│  │  ├─ services/                auth.py, profiles.py, glyphs.py, jobs.py, batches.py,
│  │  │                           learning.py, exports.py, backup.py, system.py, audit.py
│  │  ├─ api/
│  │  │  ├─ deps.py               current_user, require_role, csrf, db session
│  │  │  └─ v1/                   auth.py, system.py, profiles.py, references.py, glyphs.py,
│  │  │                           jobs.py, batches.py, tasks.py, files.py, settings.py, audit.py
│  │  ├─ schemas/                 Pydantic request/response models per resource
│  │  ├─ storage/                 filestore.py, thumbnails.py
│  │  ├─ worker/                  queue.py, runner.py, handlers/*.py
│  │  └─ engine/                  (see §3.2)
│  └─ tests/
│     ├─ fixtures/                synthetic token images + generator script, tiny profile
│     ├─ unit/                    engine/*, services/*
│     ├─ integration/             api/*
│     └─ eval/                    quality evaluation harness (metrics report)
├─ frontend/
│  ├─ package.json  package-lock.json  vite.config.ts  tsconfig.json  eslint.config.js
│  ├─ index.html
│  ├─ src/                        (see §4)
│  └─ e2e/                        Playwright specs
├─ models/                        manifest.json (+ downloaded .onnx, git-ignored)
├─ scripts/                       setup.ps1, dev.ps1, start.ps1, fetch_models.py, backup.ps1
└─ data/                          runtime data (git-ignored): traid.db, files/, backups/, logs/
```

---

## 12. Environment configuration

Loaded by `pydantic-settings` from environment and `.env` (never committed). All have safe defaults; there are **no secrets** required in MVP (session tokens are random per session; no API keys).

| Variable | Default | Purpose |
|----------|---------|---------|
| `TRAID_ENV` | `development` | `development` / `production` / `test` |
| `TRAID_HOST` | `127.0.0.1` | Bind address. Non-loopback values are refused unless `TRAID_ALLOW_REMOTE=true` (future, unsupported in MVP). |
| `TRAID_PORT` | `8765` | Port |
| `TRAID_DATA_DIR` | `./data` | DB, files, backups, logs |
| `TRAID_MODEL_DIR` | `./models` | ONNX models + manifest |
| `TRAID_DEVICE` | `auto` | `auto` / `cpu` / `directml` / `cuda` |
| `TRAID_GPU_DEVICE_ID` | `auto` | GPU adapter for DirectML/CUDA: `auto` (most dedicated VRAM) or an index. Added in Phase 4. |
| `TRAID_MAX_UPLOAD_MB` | `50` | Per-file upload limit |
| `TRAID_MAX_PIXELS` | `40000000` | Decompression-bomb guard |
| `TRAID_SESSION_IDLE_HOURS` | `12` | Idle timeout |
| `TRAID_SESSION_MAX_DAYS` | `7` | Absolute lifetime |
| `TRAID_LOG_LEVEL` | `INFO` | Logging level |
| `VITE_API_BASE` (frontend, build-time) | `/api/v1` | API base path. Never contains secrets. |

Dev: Vite on `5173` proxies `/api` to `8765`. Prod: one process on `8765` serving `frontend/dist`.

---

## 13. Error handling

- **Typed errors:** `AppError(code, http_status, message, details)` with subclasses (`NotFound`, `Conflict`, `ValidationFailed`, `Unauthorized`, `Forbidden`, `ProfileNotReady`, `EngineError`, `StorageError`). Error codes are a closed list in API.md.
- **One exception handler** maps `AppError` → error envelope; Pydantic validation → `VALIDATION_FAILED` with field details; anything else → `INTERNAL_ERROR` 500 with `request_id`, full traceback in logs only.
- **Request ID:** generated per request, returned in `X-Request-ID` and error bodies, included in all log lines.
- **Engine errors** are caught in task handlers, mapped to codes (`NO_TEXT_FOUND`, `SEGMENTATION_FAILED`, `GLYPH_MISSING`, `MODEL_UNAVAILABLE`, `IMAGE_DECODE_FAILED`, `OUT_OF_MEMORY`), saved on the task and job, never crash the worker.
- **Fallbacks:** LaMa failure → OpenCV inpaint with a quality warning (`INPAINT_FALLBACK_USED`), never silent.
- **Logging:** stdlib `logging` with JSON formatter to `data/logs/traid.log` (rotating 10 MB × 5) + console in dev. Never log passwords, session tokens, CSRF secrets, token values (old/new text) or image content. Log IDs instead.
- **Frontend:** `lib/api` converts error envelopes into typed `ApiError`; TanStack Query retries GETs twice on network errors only; React error boundary per page shows a recoverable error panel.

---

## 14. Security boundaries

| Boundary | Control |
|----------|---------|
| Network | Bind `127.0.0.1` only; `Host` header allow-list (`127.0.0.1`, `localhost`) to block DNS-rebinding; no CORS in prod (same origin); dev CORS limited to `http://localhost:5173`. |
| Browser ↔ API | Local request guard (§7.1: Origin check + required `X-Traid-Client` header on writes; session cookie + CSRF token once the optional sign-in exists); security headers: CSP (`default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'`), `X-Content-Type-Options`, `Referrer-Policy: no-referrer`. |
| Uploads | Size limit; extension and magic-byte check; full decode with Pillow under `MAX_PIXELS`; re-encoding of thumbnails; filenames never used as paths (content-hash paths only); original filename stored as display text, sanitized. |
| File serving | By file ID only, ownership checked; resolved path must be inside `data/files` (path traversal guard). |
| Database | Parameterized queries via ORM only; no raw string SQL; owner scoping. |
| Engine | Runs only on decoded arrays; no shell commands; model files checksum-verified. |
| Secrets | None required in MVP; `.env` git-ignored; frontend never receives secrets. |
| Data at rest | Local disk; owner advised to use Windows BitLocker (documented in README). |
| Audit | Append-only `audit_events` (DB triggers block UPDATE/DELETE). |

---

## 15. Testing approach

| Level | Tooling | What |
|-------|---------|------|
| Engine unit | pytest + NumPy fixtures | Each stage with synthetic images generated by `tests/fixtures/generate.py` (OFL font rendered with known perspective, blur, noise, JPEG quality, so ground truth is known). Asserts: rectification error < 1 px, segmentation box IoU > 0.8, mask-outside-unchanged bit-exact, determinism. |
| Engine quality eval | `tests/eval` harness (manual/CI-optional) | Runs on owner's evaluation set; outputs CSV + HTML report: OCR read-back rate, seam score, timing. Used for success criteria (PRD §18). |
| Service unit | pytest + in-memory SQLite | Ownership checks, learning updates, coverage/Ready rules, state transitions. |
| API integration | pytest + httpx TestClient + temp data dir | Auth flows, CSRF, validation errors, pagination, 404-on-foreign, task lifecycle (worker run synchronously in tests). |
| Frontend unit/component | Vitest + Testing Library | Primitives (states, a11y attributes), TokenInput validation, editorStore reducer/undo. |
| E2E | Playwright against prod build + fixture profile | J1 setup, J2 train (small fixture), J3 edit/accept/export, session expiry, error states. |
| Static | ruff, mypy (strict for `app/`), tsc, ESLint | Run in `scripts/check` and CI. |
| A11y | `@axe-core/playwright` on main pages | No serious/critical violations. |

Model-dependent tests are marked `@pytest.mark.models` and skipped when models are absent; a fake OCR/inpaint adapter is used for fast tests.

---

## 16. Deployment approach

**MVP target: local install on the owner's Windows PC.**

1. Prerequisites: `uv` (it installs the project's Python 3.11), Node 20.19+ LTS (required by Vite 8).
2. `scripts/setup.ps1`: `uv sync` (backend), `npm ci` + `npm run build` (frontend), `python scripts/fetch_models.py` (checksum-verified), create `data/`.
3. `scripts/start.ps1`: sets `TRAID_ENV=production`, runs Alembic upgrade (with pre-migration backup), starts Uvicorn on `127.0.0.1:8765`, opens the browser.
4. Health: `GET /api/v1/health` (liveness) and `/api/v1/system/status` (models, device, disk).
5. Updates: pull new version → rerun `setup.ps1` → `start.ps1` (migrations auto-applied after backup).

Optional (Should): CI via GitHub Actions running lint, type check and tests on push.

**Future scalability (not MVP):**
- Desktop installer (PyInstaller-built backend + Tauri/Electron shell) for one-click install.
- Multi-user/LAN: switch SQLite → PostgreSQL (SQLAlchemy/Alembic make this a config + migration change), enable Editor role, HTTPS via reverse proxy, RLS policies (DATABASE.md §7).
- GPU worker pool and Phase 2 generative engine.
