# API — Traid

**Owner:** Xavier Sun
**Status:** Draft v1.0
**Derives from:** PRD.md, ARCHITECTURE.md, DATABASE.md
**Base URL:** `http://127.0.0.1:8765/api/v1` (same origin as the SPA)

---

## 1. Conventions

### 1.1 Format
- JSON (`application/json; charset=utf-8`) unless stated (multipart uploads, binary downloads).
- Field names `snake_case`. IDs are UUID strings. Timestamps ISO-8601 UTC (`2026-10-20T14:03:11.123Z`).
- Success body: `{ "data": <object|array>, "meta"?: { … } }`.
- Error body:
```json
{ "error": { "code": "PROFILE_NOT_READY", "message": "Missing glyphs for: Q, 7", "details": { "missing": ["Q","7"] }, "request_id": "9f1c…" } }
```
- Every response carries `X-Request-ID`.

### 1.2 Status codes
| Code | Use |
|------|-----|
| 200 | OK (read/update) |
| 201 | Created |
| 202 | Accepted — background task enqueued; body = task object |
| 204 | No content (delete, logout) |
| 400 | Malformed request |
| 401 | Not authenticated / session expired |
| 403 | Authenticated but forbidden (role, CSRF failure) |
| 404 | Not found **or not owned by caller** (no existence leaks) |
| 409 | Conflict (state machine violation, duplicate, setup already done) |
| 413 | Upload too large |
| 415 | Unsupported media type |
| 422 | Validation failed (field details in `details.fields`) |
| 423 | Account locked |
| 429 | Rate limited (`Retry-After` header) |
| 500 | Internal error |
| 503 | Engine/models unavailable |

### 1.3 Error codes (closed list)
`VALIDATION_FAILED`, `UNAUTHENTICATED`, `SESSION_EXPIRED`, `FORBIDDEN`, `CSRF_FAILED`, `NOT_FOUND`, `CONFLICT`, `SETUP_ALREADY_DONE`, `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `RATE_LIMITED`, `UPLOAD_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `IMAGE_DECODE_FAILED`, `IMAGE_TOO_LARGE`, `DUPLICATE_FILE`, `INVALID_STATE`, `PROFILE_ARCHIVED`, `PROFILE_NOT_READY`, `GLYPH_MISSING`, `CHAR_NOT_IN_CHARSET`, `PATTERN_MISMATCH`, `INVALID_PATTERN`, `NO_TEXT_FOUND`, `SEGMENTATION_FAILED`, `MODEL_UNAVAILABLE`, `INPAINT_FALLBACK_USED` (warning only), `OUT_OF_MEMORY`, `TASK_INTERRUPTED`, `TASK_CANCELLED`, `STORAGE_ERROR`, `DISK_FULL`, `INTERNAL_ERROR`.

### 1.4 Validation
- Pydantic models reject unknown fields (`extra="forbid"`).
- Strings are trimmed; length limits as in DATABASE.md.
- `422` details shape: `{ "fields": [ { "path": "new_text", "code": "CHAR_NOT_IN_CHARSET", "message": "'q' is not in this profile's character set" } ] }`.

### 1.5 Pagination & filtering
- Cursor pagination on list endpoints: `?limit=` (1–100, default 25) and `?cursor=` (opaque, from `meta.next_cursor`).
- `meta`: `{ "next_cursor": "…" | null, "count": <items in page> }`. Total counts are only returned where cheap (`meta.total`).
- Default order: `created_at DESC, id DESC` unless stated.
- Filters are query parameters documented per endpoint; unknown filters → `422`.

### 1.6 Authentication & authorization
**MVP: local mode without sign-in (PRD D-03, ARCHITECTURE.md §7.1).**
- No login. Every request acts as the single local owner. Ownership is still enforced server-side; foreign resources → `404`.
- **Request guard:** a request with an `Origin` header that is not Traid's own origin → `403 CSRF_FAILED`. All `POST/PUT/PATCH/DELETE` requests must send `X-Traid-Client: web`; missing → `403 CSRF_FAILED`.
- Until the Acceptable Use notice is acknowledged (`POST /system/welcome`), endpoints other than health, system status and welcome return `403 FORBIDDEN` with `details.reason = "aup_required"`.
- "**Public**" below means callable before the AUP acknowledgement.

**Later (US-02, not MVP):** session cookie `traid_session` + `X-Traid-CSRF` token from `GET /auth/me`, as specified in §3.2.

### 1.7 Background tasks
Endpoints that start heavy work return `202` with a **Task**:
```json
{ "data": { "id": "…", "type": "render", "subject_type": "edit_job", "subject_id": "…", "status": "queued", "progress": 0, "message": null, "error_code": null, "created_at": "…", "started_at": null, "finished_at": null } }
```
Clients poll `GET /tasks/{id}` (recommended 500 ms) until `succeeded | failed | cancelled`, then re-fetch the subject.

### 1.8 Idempotency
- Accept/reject/archive are idempotent (repeating returns current state).
- `POST /batches` accepts `client_request_id`; a repeat with the same value returns the existing batch (`200`) instead of creating a duplicate.
- `POST /jobs/{id}/render` while a render task for that job is `queued|running` → returns the existing task (`202`), no duplicate work.

---

## 2. Resource shapes (abbreviated)

**User** `{ id, username, display_name, role, last_login_at, created_at }`

**Profile**
```json
{ "id": "…", "name": "Receipt Token A", "description": null,
  "surface_type": "print", "charset": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-/# ", "token_pattern": "^[A-Z]\\d-\\d{6}$", "pattern_strict": false,
  "alignment": "auto", "spacing_mode": "auto", "ready_threshold": 3, "use_auto_glyphs": false, "engine": "glyph_transplant",
  "status": "ready", "coverage": { "ready_chars": 37, "total_chars": 40, "missing": ["Q","X","#"] },
  "stats": { "glyphs_confirmed": 412, "glyphs_auto": 37, "references": 38, "jobs_accepted": 51, "acceptance_rate": 0.86 },
  "learned_params": { "blur_delta": 0.2 }, "archived_at": null, "created_at": "…", "updated_at": "…" }
```

**ReferenceImage** `{ id, profile_id, file: FileRef, known_text, status, error_code, glyph_count, conditions, created_at }`

**Glyph** `{ id, profile_id, char, status, crop_url, source: { type: "reference"|"job", id }, metrics: { cap_height_px, stroke_width_px, blur_sigma, noise_sigma, ink_color, bg_luma, contrast, angle_deg }, ocr_confidence, quality_score, use_count, accept_count, reject_count, created_at }`

**FileRef** `{ id, url: "/api/v1/files/{id}", thumb_url, mime_type, width, height, byte_size, original_name }`

**EditJob**
```json
{ "id": "…", "profile_id": "…", "batch_id": null, "status": "rendered",
  "input": { "…FileRef" }, "result": { "…FileRef" }, "mask": { "…FileRef" },
  "regions": [ { "id": "r1", "quad": [[812,233],[1190,229],[1191,281],[813,285]], "text": "A7-204913", "confidence": 0.97, "score": 0.91, "reasons": ["pattern","position"] } ],
  "selected_region_id": "r1", "selected_quad": [[812,233],[1190,229],[1191,281],[813,285]],
  "original_text": "A7-204913", "new_text": "A7-204914",
  "params": { "dx": 0, "dy": 0, "scale": 1.0, "spacing": 0, "weight": 0, "blur": 0, "ink_tone": 0, "grain": 1.0, "glyph_overrides": {} },
  "glyphs_used": [ { "position": 0, "char": "A", "source": "same_image", "glyph_id": null } ],
  "quality": { "overall": "pass", "checks": [ { "id": "ocr_readback", "status": "pass", "value": "A7-204914" }, { "id": "seam", "status": "pass", "value": 0.04, "threshold": 0.12 } ] },
  "engine_version": "glyph_transplant@1.0.0", "seed": 18342, "reject_reason": null, "error_code": null,
  "accepted_at": null, "exported_at": null, "created_at": "…", "updated_at": "…" }
```

**Batch** `{ id, profile_id, template_job_id, name, status, total_count, counts: { pending, rendered, warn, failed, accepted, rejected }, export_file: FileRef|null, created_at, finished_at }`

**AuditEvent** `{ id, user_id, action, subject_type, subject_id, details, created_at }`

---

## 3. Endpoints

### 3.1 Health & system
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | Public | Liveness: `{ "status": "ok", "version": "1.0.0" }`. No sensitive info. |
| GET | `/system/status` | Owner | Engine status: models (name, version, loaded, checksum_ok), device (`cpu`/`directml`/`cuda`), worker state, queue length, disk usage of data dir, schema revision. |
| POST | `/system/backups` | Owner | Start backup task → `202` Task. |
| GET | `/system/backups` | Owner | List backups (`FileRef` + created_at + integrity result). |

### 3.2a Welcome (MVP, replaces account setup)
| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/system/welcome` | Public | — | `{ "aup_accepted": bool, "owner": { display_name } }` |
| POST | `/system/welcome` | Public | `{ "accept_aup": true }` | `200` same shape; idempotent. Audit `system.aup_accepted`. |

### 3.2 Auth (deferred — optional password lock, US-02; not built in MVP)
| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/auth/status` | Public | — | `{ "setup_required": bool, "authenticated": bool }` |
| POST | `/auth/setup` | Public, only when no users exist | `{ username, display_name, password, accept_aup: true }` | `201` User + sets cookie. `409 SETUP_ALREADY_DONE` otherwise. |
| POST | `/auth/login` | Public | `{ username, password }` | `200` User + sets cookie. `401 INVALID_CREDENTIALS` (generic), `423 ACCOUNT_LOCKED`, `429`. |
| POST | `/auth/logout` | Auth | — | `204`, clears cookie, revokes session. |
| GET | `/auth/me` | Auth | — | `{ user, csrf_token, session_expires_at }` |
| POST | `/auth/change-password` | Auth | `{ current_password, new_password }` | `204`; revokes all other sessions. |

Validation: `username` 3–32 `^[a-z0-9_.-]+$` (lower-cased); `password` 10–128 chars, ≠ username; `accept_aup` must be `true`.

### 3.3 Profiles
| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| GET | `/profiles` | List | Filters: `archived=false|true|all` (default false), `q` (name contains). Order `updated_at DESC`. |
| POST | `/profiles` | Create | Body: `name` (req), `surface_type` (req: `print`/`paint`/`laser_mark`/`engraved`), `description`, `charset`, `token_pattern`, `pattern_strict`, `alignment`, `spacing_mode`, `ready_threshold`, `use_auto_glyphs`. `409` on duplicate name. `422 INVALID_PATTERN`. |
| GET | `/profiles/{id}` | Detail | Includes `status`, `coverage`, `stats`. |
| PATCH | `/profiles/{id}` | Update | Any create field. Archived profiles → `409 PROFILE_ARCHIVED` except unarchive. |
| POST | `/profiles/{id}/archive` | Archive | Idempotent. |
| POST | `/profiles/{id}/unarchive` | Restore | Idempotent. |
| DELETE | `/profiles/{id}` | Permanent delete | Only archived profiles; body `{ "confirm_name": "<name>" }` must match; `409` if any batch is running or jobs reference it unless `?with_jobs=true` (deletes its jobs too). Audit `profile.deleted`. |
| GET | `/profiles/{id}/coverage` | Coverage matrix | `[{ char, confirmed, auto, rejected, best_quality, ready }]` |
| GET | `/profiles/{id}/learning` | Learning stats | Acceptance rate series (last 50 jobs), most-rejected glyphs, learned params. (Should) |

### 3.4 Reference images
| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| POST | `/profiles/{id}/references` | Upload 1–50 images | `multipart/form-data`, field `files[]`, optional `known_text[]` aligned by index. Response `202`: `{ data: { created: [ReferenceImage], skipped: [{ name, code: "DUPLICATE_FILE" }], rejected: [{ name, code }] , task: Task } }`. One `extract_glyphs` task per upload request. |
| GET | `/profiles/{id}/references` | List | Filters: `status`. Cursor-paginated. |
| PATCH | `/references/{id}` | Set `known_text` | Triggers re-extraction task (`202`) if processed. |
| POST | `/references/{id}/reextract` | Re-run extraction | `202` Task. Replaces this reference's `auto` glyphs; keeps `confirmed`/`rejected` decisions. |
| DELETE | `/references/{id}` | Remove reference | Cascades its glyphs. `204`. |

### 3.5 Glyphs
| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| GET | `/profiles/{id}/glyphs` | List | Filters: `char` (exact), `status` (csv), `min_quality` (0–1), `source` (`reference`/`job`). Order: `char ASC, quality_score DESC`. Limit up to 200. |
| PATCH | `/glyphs/{id}` | Update one | `{ status?, char? }`; `char` must be in charset. |
| POST | `/profiles/{id}/glyphs/bulk` | Bulk update | `{ ids: [≤ 500], action: "confirm"|"reject"|"relabel", char? }` → `{ updated: n }`. |
| GET | `/jobs/{id}/glyph-candidates` | Real characters from a job's original image offered for the bank (Should) | Only for accepted jobs. |
| POST | `/jobs/{id}/glyph-candidates/accept` | Add chosen candidates (Should) | `{ candidate_ids: [] }` → creates glyphs `status=confirmed`, `source_job_id`. |

### 3.6 Edit jobs
| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| POST | `/jobs` | Create from target image | `multipart`: `file`, `profile_id`. Validates file (§5). → `202` `{ job: EditJob, task: Task(detect) }`. Profile may be not-ready (detection still useful); render will enforce coverage. |
| GET | `/jobs` | History list | Filters: `profile_id`, `status` (csv), `quality` (`pass|warn|fail`), `from`, `to` (dates), `q` (token prefix search on old/new text), `include_batch_items` (default false). |
| GET | `/jobs/{id}` | Detail | Full EditJob. |
| PUT | `/jobs/{id}/region` | Select/adjust region | `{ region_id?: string, quad?: [[x,y]×4] }` (one required; quad must be convex, inside image bounds, area ≥ 64 px²). Allowed in `detected|rendered|rejected` → status `detected`, invalidates cache. Returns EditJob with re-read `original_text`. |
| POST | `/jobs/{id}/render` | Generate / re-generate | `{ new_text, params? }`. Validates charset/pattern/coverage synchronously → `422 CHAR_NOT_IN_CHARSET` / `PATTERN_MISMATCH` (strict only) / `409 PROFILE_NOT_READY` with `details.missing`. Otherwise `202` Task(render). Params ranges: `dx,dy` −50…50 px; `scale` 0.8–1.2; `spacing` −10…10 px; `weight` −1…1; `blur` −2…2 σ; `ink_tone` −1…1; `grain` 0–3; `glyph_overrides` `{ "<position>": "<glyph_id>" }`. |
| GET | `/jobs/{id}/glyph-variants?position=n` | Alternatives for one character (Should) | Top 6 glyphs with similarity scores. |
| POST | `/jobs/{id}/accept` | Accept | Only from `rendered`. Applies learning update + audit in one transaction. Idempotent on `accepted`. |
| POST | `/jobs/{id}/reject` | Reject | `{ reason? (≤ 300) }`. From `rendered`. Updates glyph reject counts. |
| POST | `/jobs/{id}/export` | Produce export file | `{ format?: "original"|"jpeg"|"png"|"tiff", filename_pattern? }`. Only `accepted`. Sync (fast) → `201` `{ file: FileRef, download_name }`. Audit `job.exported`. |
| POST | `/jobs/{id}/reopen` | Copy into a new editable job (same input, region, params) | `201` EditJob. |
| DELETE | `/jobs/{id}` | Delete job | Not allowed for batch items of running batches (`409`). `204`. Audit `job.deleted`. |

### 3.7 Batches (Should)
| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| POST | `/batches/validate` | Dry-run validation | `{ profile_id, values: [string ≤ 1000] }` → `{ valid: [], invalid: [{ value, code }], duplicates: [] }`. |
| POST | `/batches` | Create & start | `{ template_job_id, values: [1–1000 valid], name?, client_request_id? }`. Template must be `rendered` or `accepted`; its region and params are copied. → `202` `{ batch, task: Task(batch_run) }`. |
| GET | `/batches` | List | Cursor-paginated. |
| GET | `/batches/{id}` | Detail with counts | |
| GET | `/batches/{id}/items` | Items (EditJob summaries) | Filters: `status`, `quality`. Default order: `quality_overall` (fail, warn, pass) then position. |
| POST | `/batches/{id}/cancel` | Cancel | Finished items kept. Idempotent. |
| POST | `/batches/{id}/accept-passed` | Accept all items with `quality=pass` in `rendered` | `{ accepted: n }` |
| POST | `/batches/{id}/export` | ZIP accepted items | `202` Task(batch_export) → `export_file` on batch. File names from pattern, collisions suffixed `_2`. |

Batch item review uses the normal `/jobs/{id}` endpoints.

### 3.8 Tasks
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/tasks/{id}` | Task status/progress |
| GET | `/tasks?status=queued,running` | Active tasks (Tasks chip) |
| POST | `/tasks/{id}/cancel` | Request cancellation (honoured between stages) |
| POST | `/tasks/{id}/retry` | Re-enqueue a `failed` task (same payload) → `202` new Task |

### 3.9 Files
| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| GET | `/files/{id}` | Download/view binary | Ownership checked. `Content-Type` from DB, `Content-Disposition: inline` (images) or `attachment` with sanitized name (exports, zips, backups; `?download=1` forces attachment). `Cache-Control: private, max-age=31536000, immutable`. |
| GET | `/files/{id}/thumb?size=256|512` | Thumbnail (generated on first request, cached) | JPEG/PNG. |

### 3.10 Settings & audit
| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| GET | `/settings` | All settings with defaults applied | |
| PATCH | `/settings` | Update | Keys: `export.default_format` (`original|jpeg|png|tiff`), `export.filename_pattern` (tokens `{template}`, `{token}`, `{date}`, `{n}`; ≤ 120 chars; only `[A-Za-z0-9_{}.-]`), `export.metadata_marker` (bool), `export.jpeg_quality_mode` (`match_source|fixed:<60–100>`), `storage.backup_retention` (1–50). Audit `settings.updated`. |
| GET | `/audit` | Audit log | Filters: `action` (csv), `from`, `to`. Cursor-paginated. Read-only. |

---

## 4. External APIs & integrations

**None at runtime.** Traid makes no outbound network requests while running.

| Integration | Mode | Failure handling |
|-------------|------|------------------|
| Model download (`scripts/fetch_models.py`) | Setup-time CLI, pinned HTTPS URLs from `models/manifest.json` | Retries 3× with backoff; streams to temp file; verifies SHA-256; on mismatch deletes file and exits non-zero. App starts without models but `/system/status` reports `MODEL_UNAVAILABLE` and engine endpoints return `503`. |
| ONNX Runtime providers | In-process | Provider init failure (DirectML/CUDA) → automatic fallback to CPU, logged and shown in status. |

**Webhooks:** none. There are no inbound third-party calls, so no signature verification is needed. If a future integration requires webhooks, it must verify HMAC signatures with a secret from environment variables and reject replays by timestamp (±5 min).

---

## 5. Uploads

| Rule | Value |
|------|-------|
| Accepted types | JPEG, PNG, TIFF (8-bit per channel; RGB, RGBA, grayscale) — verified by magic bytes **and** full decode, not by extension |
| Max size | `TRAID_MAX_UPLOAD_MB` (default 50 MB) per file → `413` |
| Max pixels | `TRAID_MAX_PIXELS` (default 40 MP) → `422 IMAGE_TOO_LARGE` |
| Files per request | 1 (`/jobs`), 1–50 (`/references`) |
| Names | Original name sanitized for display; storage path from SHA-256 only |
| Duplicates | Same SHA-256 and kind → reuse existing file row; references report `DUPLICATE_FILE` in `skipped` |

---

## 6. Rate limiting & abuse protection

Local single user, so limits target brute force and runaway clients, not traffic.

| Scope | Limit | Response |
|-------|-------|----------|
| `POST /auth/login` (deferred) | 10 / minute per client IP; account lock after 5 consecutive failures for 5 min | `429` (`Retry-After`) / `423` |
| Task-creating endpoints | Max 200 queued tasks per user; max 1 running batch | `429 RATE_LIMITED` / `409` |
| Upload endpoints | 30 requests / minute | `429` |

Implemented in-process (token bucket in memory) — no external store.

---

## 7. Environment variables

Server-side only (see ARCHITECTURE.md §12 for defaults):
`TRAID_ENV`, `TRAID_HOST`, `TRAID_PORT`, `TRAID_DATA_DIR`, `TRAID_MODEL_DIR`, `TRAID_DEVICE`, `TRAID_GPU_DEVICE_ID` (Phase 4), `TRAID_MAX_UPLOAD_MB`, `TRAID_MAX_PIXELS`, `TRAID_SESSION_IDLE_HOURS`, `TRAID_SESSION_MAX_DAYS`, `TRAID_LOG_LEVEL`, `TRAID_DEV_PASSWORD` (dev seed only; refused in production).

Frontend (build-time, public): `VITE_API_BASE`. **No secret may ever be exposed through a `VITE_` variable.**

MVP requires no API keys or secrets.

---

## 8. Data privacy & failure handling

- Responses never include password hashes, session token hashes, CSRF secrets of other sessions, storage paths or stack traces.
- Logs record method, path template (not raw query values), status, duration, request ID, user ID. Never request bodies, token values or file contents.
- `GET /files/{id}` is the only way to read binaries; there is no directory listing.
- Engine failures are captured on the task (`error_code`, safe `message`) and the job (`status=failed`, `error_code`); the API stays available.
- Worker crash/restart → interrupted tasks become `failed` with `TASK_INTERRUPTED`; clients see this via polling and can `retry`.
- Disk full during write → `500 DISK_FULL` with a path-free message; partially written files are removed.
- All multi-row changes (accept + learning + audit; bulk glyph updates; profile delete) run in single DB transactions.
- Frontend handles: `403` with `aup_required` → Welcome screen; `503` → engine-offline banner; network error → retry twice for GETs, never auto-retry POSTs.
