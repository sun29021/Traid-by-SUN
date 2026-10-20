# IMPLEMENTATION PLAN — Traid

**Owner:** Xavier Sun
**Status:** Draft v1.0
**Inputs:** PRD.md, DESIGN.md, ARCHITECTURE.md, DATABASE.md, API.md, AGENTS.md
**Rule:** foundations first; each task is small enough to implement and verify on its own; nothing beyond the documented MVP.

Legend: **M** = Must (MVP), **S** = Should. Migration names match DATABASE.md §9.

---

## Phase 0 — Approvals & repository setup

**Goal:** owner decisions recorded; empty but runnable, linted, type-checked monorepo.

| Task | Detail |
|------|--------|
| 0.1 | Owner answers PRD §20 decisions D-01…D-10 and §21 open questions; record answers in PRD.md. |
| 0.2 | `git init`, `.gitignore`, `README.md` skeleton, `.env.example`. |
| 0.3 | Backend scaffold: `pyproject.toml` (uv), FastAPI app factory, `/api/v1/health`, ruff + mypy config, pytest config. |
| 0.4 | Frontend scaffold: Vite + React + TS strict, ESLint + Prettier, Vitest, Playwright config; dev proxy `/api` → 8765. |
| 0.5 | `scripts/dev.ps1` (both servers), `scripts/check.ps1` (ruff, mypy, pytest, eslint, tsc, vitest). |

- **Files:** root config files, `backend/pyproject.toml`, `backend/app/main.py`, `frontend/*` config, `scripts/*`.
- **Prerequisites:** Python 3.11, Node 20, uv installed.
- **DB/API:** `GET /health` only.
- **Tests:** health endpoint test; one placeholder Vitest render test of `App`.
- **Done when:** `scripts/dev.ps1` serves the SPA calling `/health`; `scripts/check.ps1` passes.
- **Status (2026-10-20): DONE.** Also delivered early: 1.1 config, 1.2 JSON logging + request IDs, 1.3 error envelope, plus `scripts/setup.ps1`, the app shell with base routing and the design tokens. Playwright is deferred to Phase 3, where the first E2E test lands (no unused dependency now).

## Phase 1 — Backend foundation

**Goal:** config, logging, errors, DB, file storage and task worker that every feature builds on.

| Task | Detail |
|------|--------|
| 1.1 | `core/config.py` (pydantic-settings, all env vars in ARCHITECTURE §12, loopback-only host guard). |
| 1.2 | `core/logging.py` (JSON logs, rotation, request ID middleware, redaction rules). |
| 1.3 | `core/errors.py` (AppError hierarchy, error envelope handler, closed error-code enum). |
| 1.4 | `db/engine.py` (SQLite pragmas), Alembic setup, migration `0001_initial_auth`: `users`, `sessions`, `audit_events` (+ triggers), `app_settings`. |
| 1.5 | `storage/filestore.py` + migration `0002_files_tasks`: `files`, `tasks`; content-addressed save, path guard, upload validation (magic bytes, decode, pixel cap). |
| 1.6 | `worker/` single-thread runner: claim, progress, cancel, startup recovery (`TASK_INTERRUPTED`); synchronous mode for tests. |
| 1.7 | Security middleware: Host allow-list, security headers/CSP, dev-only CORS. |

- **Depends on:** Phase 0.
- **Tests:** config validation; error envelope shapes; migration up/down on temp DB; audit trigger blocks UPDATE/DELETE; file store dedupe + traversal guard + bad-file rejection; worker claim/cancel/recovery.
- **Done when:** app starts with migrations applied, logs in JSON, rejects non-local Host headers; all tests pass.
- **Status (2026-10-20): DONE.** Migrations `0001_initial_auth`, `0002_files_tasks`; file storage + upload validation (`storage/`, `services/files.py`); task queue (`worker/queue.py`) + single-thread runner (`worker/runner.py`, handler registry empty until Phase 5); Host guard, CSP and security headers. No new HTTP endpoints: `/tasks/*` and upload endpoints need authentication, so they arrive with Phase 2 and Phase 5 per API.md. Deferred to 13.3: automatic pre-migration backup. Dev seed data (DATABASE.md §10) needs profiles, so it arrives in Phase 5.

## Phase 2 — Local owner, request guard & audit

**Rescoped 2026-10-20:** the owner chose no sign-in for now (PRD D-03). Password sign-in moved to the optional "Later" section at the end.

**Goal:** single local owner, protection from other websites, Acceptable Use acknowledgement, audit log (PRD US-01; ARCHITECTURE §7.1; API §1.6, §3.2a).

| Task | Detail |
|------|--------|
| 2.1 | Migration `0003_local_owner`: `users.password_hash` nullable. Startup creates the single owner (`owner`, "Xavier Sun") if no user exists. |
| 2.2 | `api/deps.py`: DB session dependency, `current_user` (the local owner), `require_aup`. |
| 2.3 | Local request guard middleware: Origin allow-list + required `X-Traid-Client: web` on writes → `403 CSRF_FAILED`. Frontend client sends the header. |
| 2.4 | `GET/POST /system/welcome`, `GET /system/status` (owner-level status without models until Phase 4). |
| 2.5 | `services/audit.py` + `GET /audit` (cursor pagination); `GET /tasks/{id}`, `GET /tasks`, cancel, retry endpoints on top of the Phase 1 queue. |

- **Tests:** owner auto-created once; foreign Origin → 403; write without header → 403; form-style cross-site POST → 403; AUP gate → 403 until accepted, then 200; audit events written and immutable; task endpoints incl. cancel/retry and 404 for unknown IDs.
- **Done when:** every later router can depend on `current_user` and `require_aup`; no other website can change data.
- **Status (2026-10-20): DONE.** Migration `0003_local_owner`; owner bootstrap (`services/owner.py`); request guard (`core/http_security.py`); deps (`api/deps.py`: session, `current_user`, `require_aup`, unknown-query rejection, CSV enum filters); keyset cursor pagination (`core/pagination.py`, `repositories/pagination.py`); audit service + `GET /audit`; `GET /tasks`, `GET /tasks/{id}`, cancel, retry; `GET /system/status`, `GET/POST /system/welcome`. Frontend client sends `X-Traid-Client`. 107 backend tests.

## Later (optional) — Password lock (PRD US-02)

Argon2id passwords, sessions, CSRF token, lockout, rate limiting, Sign-in page and `RequireAuth` exactly as ARCHITECTURE §7.2 and API §3.2 describe. Not scheduled; build only when the owner asks.

## Phase 3 — Frontend shell & design system

**Goal:** DESIGN.md implemented as tokens + primitives; app shell, routing, auth screens.

| Task | Detail |
|------|--------|
| 3.1 | `styles/tokens.css`, reset, bundled IBM Plex fonts. |
| 3.2 | Primitives: Button, IconButton, Input, TokenInput (shell), Select, Checkbox, Toggle, Slider+NumberField, Badge, MetricRow, Table, Tabs, Dialog, Drawer, Toast, Banner, Tooltip, Skeleton, EmptyState, ProgressBar, DropZone. |
| 3.3 | `lib/api` client: envelope parsing, `ApiError`, `X-Traid-Client` header, 403 `aup_required` / 503 handling; OpenAPI type generation script. |
| 3.4 | AppShell: nav rail (with "by Xavier Sun"), top bar, Tasks chip placeholder, engine-offline banner; router with placeholder pages; 404/forbidden pages. |
| 3.5 | Welcome page (engine check + Acceptable Use), shown until acknowledged. |

- **Depends on:** Phase 2 API.
- **Tests:** primitive state/a11y tests; api client error mapping; Playwright: first run → Welcome → accept → Home; axe check on Welcome.
- **Done when:** first run shows Welcome, then the app; all pages reachable as placeholders; no hard-coded style values (lint rule or review).
- **Status (2026-10-20): DONE.** 21 primitives in `src/components` (Field, TextField, Select, Checkbox/Toggle, TokenInput, AdjustmentField, Button, IconButton, Tooltip, Badge, MetricRow, ProgressBar, Skeleton, Banner, Table, Tabs, Dialog/Drawer, Toast, DropZone, EmptyState); generated API types + `apiList`/`queryString`; AUP redirect via QueryCache; engine-offline banner; tasks chip; G-key shortcuts; route error page; Welcome page + gate with safe `next` redirect. 39 unit tests; 3 Playwright E2E tests with axe (0 serious/critical violations). TypeScript pinned to 5.x (see ARCHITECTURE §2.2). Shortcut sheet (`?`) and command palette remain "Should" items for later phases.

## Phase 4 — Engine I: image I/O, models, detection, geometry

**Goal:** detect and read text in any supported image; rectify a region.

| Task | Detail |
|------|--------|
| 4.1 | `tests/fixtures/generate.py`: synthetic token images with ground truth (quad, text, blur, noise, JPEG quality) for every surface type: ink on paper, paint on a wall-like texture, laser mark and embossed/engraved text on brushed-metal and plastic textures (relief simulated with a height map + directional light). |
| 4.2 | `engine/io.py`: decode/encode preserving ICC + DPI; JPEG quality estimate. |
| 4.3 | `models/manifest.json` + `scripts/fetch_models.py` (checksums) + `engine/models.py` (lazy sessions, device select, CPU fallback). Use `onnxruntime-directml`; add `TRAID_GPU_DEVICE_ID` (auto = adapter with most dedicated VRAM, i.e. the RTX 3050 on the owner's laptop); OOM on GPU retries once on CPU. |
| 4.4 | `engine/detect.py` (PP-OCRv4 DB + CTC on ONNX Runtime, own pipeline) → `Region` list; fake detector adapter for fast tests. |
| 4.5 | `engine/geometry.py` rectify/inverse warp. |
| 4.6 | `GET /system/status` (models, device, queue, disk). |

- **Tests:** IO round-trip keeps size/DPI/ICC; quality estimate ±5; detection finds fixture tokens (models mark); rectification corner error < 1 px; status endpoint.
- **Done when:** a fixture image yields correct regions + text; status shows model/device.
- **Status (2026-10-20): DONE.** `engine/io.py` (ICC/DPI kept, JPEG re-encoded with the source's own quantisation tables and subsampling, EXIF orientation applied and never copied, quality estimate ±2), `engine/geometry.py`, `engine/models.py` (manifest, cached checksums, lazy sessions, DirectML high-performance GPU with CPU fallback at creation and run time), `engine/detect.py` (own PP-OCRv4 pipeline, see ARCHITECTURE §2.1), `scripts/fetch_models.py`, `/system/status` engine section, fixture generator for all four surfaces. Result on fixtures: 12/12 tokens read exactly across print/paint/laser/engraved, box IoU 0.83–0.93. Known limit: PP-OCR rarely emits spaces → recovered in task 5.3.

## Phase 5 — Profiles, references & glyph extraction

**Goal:** PRD J2 backend: create profiles, upload references, extract glyphs in the background.

| Task | Detail |
|------|--------|
| 5.1 | Migration `0004_profiles_glyphs` (0003 became `0003_local_owner`): `profiles`, `reference_images`, `glyphs`. |
| 5.2 | Profiles service + API (CRUD, archive, delete with confirm, derived status, coverage). Regex validation for `token_pattern`. |
| 5.3 | `engine/segment.py` (char boxes, baseline, cap height, pitch; **recover spaces from ink gaps**, because PP-OCR rarely outputs them — CTC time steps are too coarse, measured in Phase 4) and `engine/matte.py` (ink mode: soft alpha; relief mode: rim-dilated mask + texture patch + lighting direction). Migration adds `profiles.surface_type` and `glyphs.light_dir_deg`. |
| 5.4 | `extract_glyphs` task handler: detect → filter by charset → rectify → segment → matte → glyph rows + PNG crops; per-reference status/error; known-text alignment (S). |
| 5.5 | References API (upload multi-file with dedupe, list, patch known_text, re-extract, delete) and glyph API (list/filter, patch, bulk). |

- **Tests:** segmentation IoU > 0.8 on fixtures; matte alpha error small vs ground truth; coverage + Ready rule; status derivation; upload dedupe/rejections; bulk relabel validation; ownership 404s.
- **Done when:** uploading fixture references produces reviewable glyphs and correct coverage via API.
- **Status (2026-10-20): DONE.** `engine/segment.py` (ink map from a large median background; relief mode keeps highlights and shadows; components → column groups reconciled with the label count; touching characters split near the middle; narrow single strokes never split), `engine/matte.py` (ink: colour-line alpha against an inpainted background; relief: rim mask + light direction; metrics: stroke, blur, noise, ink colour, contrast, isolation, quality), `engine/extract.py`, migration `0004_profiles_glyphs`, profile/reference/glyph services and API, `GET /files/{id}` + thumbnails (from 9.4), `extract_glyphs` task. Measured on fixtures (true labels): character-box IoU median 0.90–0.91 for print/paint/laser with 0–1 bad lines of 24; engraved median 0.77 (rims are part of the glyph). **Decision:** spaces are not inferred from ink gaps — measured gap distributions of real spaces and narrow-glyph letter gaps overlap — they come from OCR, known text or the pattern. 230 backend tests.

## Phase 6 — Profile UI (training & review)

**Goal:** PRD J2 end-to-end in the UI (US-10…US-16).

| Task | Detail |
|------|--------|
| 6.1 | Profiles list + create dialog. |
| 6.2 | Profile detail with URL tabs; Overview (stats). |
| 6.3 | References tab: drop zone, per-file progress, status grid, detail drawer. |
| 6.4 | Glyphs tab: filter column, grouped GlyphGrid with keyboard review and bulk bar. |
| 6.5 | Coverage tab + Settings tab form. |
| 6.6 | Tasks chip + `useTask` polling. |

- **Tests:** GlyphGrid keyboard interactions; form validation; Playwright: create profile → upload fixtures → confirm glyphs → profile Ready.
- **Done when:** a fixture profile can be trained to Ready purely through the UI.
- **Status (2026-10-20): DONE.** Profiles list + create dialog (surface picker, charset presets, pattern), profile detail with URL tabs (`/profiles/:id/:tab`): Overview with next-step guidance, References (multi-file drop, extraction progress via `useTask`, cards, drawer with known text / re-extract / delete), Glyphs (filter column, grouped keyboard-reviewable listbox, bulk bar), Coverage matrix, Settings (all fields, archive/restore, typed-name delete). 50 unit tests; Playwright trains a profile to Ready with the real models and axe finds no serious violations on any profile screen. Decisions: Delete (not X) rejects glyphs; glyph checkerboard follows the original surface brightness; draft status shown as "Not ready".

## Phase 7 — Engine II: text removal

**Goal:** clean removal of the old token (FR-E06).

| Task | Detail |
|------|--------|
| 7.1 | `engine/inpaint.py`: removal mask from glyph alphas (dilation), LaMa ONNX with tiling/cropping around the region, OpenCV fallback flagged in report. |

- **Tests:** pixels outside mask bit-identical; residual-text check (OCR finds no text in removed area) on fixtures; fallback path.
- **Done when:** fixtures show removed tokens with no ghosting at 100% zoom (visual check) and tests pass.
- **Status (2026-10-20): DONE.** `engine/inpaint.py` hybrid remover: Telea fill + per-channel grain top-up on plain surfaces, LaMa (OpenCV Zoo ONNX, CPU only) when long edges cross into the mask, feathered blend with outside pixels bit-identical. Fixture generator can render the same scene without ink (`blank`) and with a crossing rule line (`rule`), giving true backgrounds. Measured (ARCHITECTURE §10.1): plain structure error 1.0–1.8, texture ratio 0.81–0.89; with a crossing line LaMa 0.7–1.6 vs Telea 3.5–8.9. OCR finds no text after removal on all four surfaces. `fetch_models.py` gained `url` sources; `ModelSpec.cpu_only`. 246 backend tests.

## Phase 8 — Engine III: synthesis, harmonization, verification

**Goal:** natural replacement + quality report (FR-E07…E14).

| Task | Detail |
|------|--------|
| 8.1 | `engine/glyph_select.py` (same-image first, bank ranking incl. learned score; `GLYPH_MISSING`). |
| 8.2 | `engine/layout.py` (slot reuse; alignment/spacing modes). |
| 8.3 | `engine/harmonize.py` (scale, ink colour, shading transfer, blur match, seeded grain; relief mode: low-frequency illumination swap). |
| 8.4 | `engine/composite.py` (ink mode: feathered alpha; relief mode: Poisson `seamlessClone`; both: hard mask enforcement). Tests cover every surface type. |
| 8.5 | `engine/verify.py` (OCR read-back, seam score, inside/outside stats → QualityReport). |
| 8.6 | `engine/pipeline.py` with `Synthesizer` interface + `GlyphTransplantSynthesizer`; artefact caching contract. |
| 8.7 | `tests/eval` harness producing CSV/HTML metrics report. |

- **Tests:** determinism (same seed → identical bytes); OCR read-back on fixtures ≥ 98%; no system-font path exists; outside-mask unchanged; timing budget smoke test.
- **Done when:** eval harness on fixtures meets thresholds; owner reviews a sample of real-image results.

## Phase 9 — Edit jobs backend

**Goal:** PRD J3 API (API §3.6).

| Task | Detail |
|------|--------|
| 9.1 | Migration `0004_edit_jobs`: `edit_jobs`, `edit_job_glyphs`. |
| 9.2 | Jobs service with state machine; `POST /jobs` (+ detect task with candidate scoring `engine/candidates.py`), `PUT /region`, `POST /render` (sync validation + render task, cache reuse), accept/reject, reopen, delete. |
| 9.3 | Export service: format/DPI/ICC preservation, JPEG quality match, metadata marker setting, filename pattern; audit. |
| 9.4 | ~~`GET /files/{id}` + thumbnails~~ — delivered early in Phase 5 (the glyph review UI needs them). |

- **Tests:** full state machine incl. invalid transitions (409); render validation codes; render dedupe (existing task returned); export preserves properties; marker on/off; ownership 404s.
- **Done when:** a job can go upload → detect → render → accept → export via API.

## Phase 10 — Editor UI

**Goal:** PRD J3 in the UI (US-20…US-31).

| Task | Detail |
|------|--------|
| 10.1 | Canvas viewer: ImageBitmap, zoom/pan, pixel-accurate ≥ 100%, status bar. |
| 10.2 | SVG overlay: detected/selected regions, corner handles, keyboard nudging; Regions panel (accessible mirror). |
| 10.3 | Inspector: profile select, old token, TokenInput validation, Generate with step progress. |
| 10.4 | Before/after toggle + split slider + mask/glyph overlays; result cross-fade. |
| 10.5 | Adjustments panel + `editorStore` with undo/redo (S) and re-render. |
| 10.6 | Quality report panel; Accept/Reject/Export flow; unsaved-result guard. |
| 10.7 | Character chips + glyph variant picker (S). |
| 10.8 | Home page: drop zone → editor, recent jobs, profiles summary. |

- **Tests:** editorStore reducer + undo; TokenInput; hotkeys; Playwright: drop fixture → auto-selected region → type token → generate → accept → export file downloaded; profile-not-ready banner; detection-failed manual region path.
- **Done when:** J3 completes in ≤ 5 interactions on a fixture; keyboard-only run possible.

## Phase 11 — Learning loop

**Goal:** Traid improves with use (FR-P05, FR-P06, US-52, US-53).

| Task | Detail |
|------|--------|
| 11.1 | `services/learning.py`: glyph counters, learned_params EMA, typical_region update — inside accept/reject transactions. |
| 11.2 | Candidate scoring uses `typical_region`; render starts from `learned_params`. |
| 11.3 | `GET /profiles/{id}/learning` + Overview chart (S). |
| 11.4 | Glyph candidates from accepted jobs' original pixels (S). |

- **Tests:** counters/EMA math; rejected glyphs rank lower; harvested glyphs only come from input files, never results.
- **Done when:** repeated accepts measurably change selection and defaults in tests.

## Phase 12 — Batch (S)

**Goal:** PRD J4 (US-40…US-43).

| Task | Detail |
|------|--------|
| 12.1 | Migration `0005_batches`: `batches`. |
| 12.2 | Batch service + API: validate, create (idempotent), `batch_run` handler reusing template background, cancel, accept-passed, `batch_export` ZIP. |
| 12.3 | Batch UI: steps, values input/import, validation list, progress, review grid + drawer, export. |

- **Tests:** validation dry-run; idempotent create; cancel keeps finished items; ZIP naming collisions; Playwright 10-value batch.
- **Done when:** 100-value fixture batch completes within throughput target and exports a correct ZIP.

## Phase 13 — History, settings, backup

**Goal:** US-50, US-51, US-54, US-55, FR-U04, FR-U05.

| Task | Detail |
|------|--------|
| 13.1 | History page: filters in URL, search, cursor pagination; job detail page. |
| 13.2 | Settings: Account (change password), Engine (status), Export defaults, Storage & backup, Audit log, About (credits, model licenses, AUP). |
| 13.3 | Backup task + list + `scripts/backup.ps1`; pre-migration backup on start; orphan file sweep; README restore steps. |

- **Tests:** filters/pagination; settings validation; backup integrity check; restore procedure tested manually once and documented.
- **Done when:** all MVP screens in PRD §11 are complete.

## Phase 14 — Hardening & release

**Goal:** production-ready local release.

| Task | Detail |
|------|--------|
| 14.1 | QA pass over all PRD loading/empty/error states (§15). |
| 14.2 | Security audit vs ARCHITECTURE §14 (uploads, CSRF, headers, logs redaction, dependency audit `pip-audit`/`npm audit`). |
| 14.3 | Performance tuning to PRD §9 targets on owner hardware. |
| 14.4 | Accessibility pass (axe + keyboard walkthrough). |
| 14.5 | `scripts/setup.ps1` / `start.ps1` production flow; README final. |

- **Done when:** all checks pass; production build runs from a clean checkout on the owner's PC.

## Phase 15 — Showcase evaluation

**Goal:** evidence for PRD §18 success criteria.

| Task | Detail |
|------|--------|
| 15.1 | Run eval harness on owner's evaluation set (≥ 100 edits); export metrics report. |
| 15.2 | Blind-test kit: randomized real/edited pairs + simple scoring sheet. |
| 15.3 | Demo script covering J2 → J3 → J4 → learning stats. |

---

## Dependency order

```
P0 → P1 → P2 → P3
          P1 → P4 → P5 → P6 (needs P3)
                    P5 → P7 → P8 → P9 → P10 (needs P3) → P11 → P12 → P13 → P14 → P15
```
P4/P5 (engine + profiles backend) can proceed in parallel with P3 (frontend shell) once P2 is done.

## Mapping to your prompt pack

| Your prompt | Phase |
|-------------|-------|
| 8. Project setup | Phase 0 (+ 1.1–1.3) |
| 10. Database & backend connection | Phase 1, then migrations in 5/9/12 |
| 11. Authentication & authorization | Phase 2 (local owner + request guard, no sign-in) and 3.5 (Welcome); password lock is optional "Later" |
| 9. Feature development | One task at a time from Phases 3–13 |
| 13. External API / service integration | 4.3 (model fetch) — no runtime external APIs |
| 12. MCP connection | Not required by the architecture; only if you want dev tooling |
| 14. Testing & QA, 16. Security audit, 17. Code review | Phase 14 (and after each phase) |
| 18. Deployment, 19. Monitoring | 14.5 + local logs/health (no hosted monitoring in MVP) |
| 20. Final production audit | After Phase 14, before Phase 15 |

---

## Recommended first task

**Task 0.1 — record the owner decisions (PRD §20, D-01…D-10 and §21 questions)**, then **Task 0.2–0.5 (project setup, prompt 8)**. The decisions that change code most are D-02 (local web app vs. desktop app), D-04 (glyph-transplant engine first) and D-07 (character set); everything else can default to the recommendation.
