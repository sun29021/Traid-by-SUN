# PRD — Traid

**Product:** Traid — style-matched token text replacement
**Author / Owner:** Xavier Sun
**Document status:** v1.0 — decisions approved 2026-10-20 (see §20); open questions in §21 remain
**Last updated:** 2026-10-20
**Source of truth for:** scope, behavior and acceptance criteria. DESIGN.md, ARCHITECTURE.md, DATABASE.md, API.md and AGENTS.md derive from this document. If they conflict with this PRD, this PRD wins until it is amended.

---

## 1. Summary

Traid is a focused desktop-class application that replaces a short printed text string (a "token": e.g. `A7-204913`) inside a photo or scan with a new string, so that the new characters match the original font, ink, texture, lighting, blur, perspective and noise of that exact image.

It is **not** a general photo editor. It does one job: *find the token, remove it cleanly, re-print a new token in the same style, and let the user verify the result.*

Traid gets better over time by building a **Style Profile** from the user's own real images of the same token design. Instead of drawing characters with a generic font or asking a generative model to "imagine" them, Traid reuses **real character samples** (glyphs) extracted from real photos and adapts them to the target image. This is the same technique professional retouchers use manually (cloning a real "7" from elsewhere on the page), made automatic.

---

## 2. Problem

| # | Problem | Evidence (from owner) |
|---|---------|------------------------|
| P1 | Editing small printed letters/numbers looks fake: wrong font weight, too sharp/too soft, wrong ink colour, flat lighting, misaligned perspective. | "whenever I try to edit it, it feels AI-generated or not blended properly" |
| P2 | Generic AI editors (generative fill, text-replace tools) invent glyph shapes that do not match the real print. | Same as above |
| P3 | Doing it properly in Photoshop by hand is slow and needs expert skill for every single token. | "like how professional Photoshop editors do their job … but easy and automatic" |
| P4 | The work is repetitive: same token design, many different numbers. | "I have tokens numbers and I have to put them in a page where already a token is there" |

---

## 3. Value proposition

> **Drop an image, type the new token, get a replacement that matches the real print — in seconds, verified, and improving with every image you train it on.**

Differentiators:
1. **Real glyphs, not imagined ones.** Characters come from the user's own photographed samples of the same font.
2. **Image-aware adaptation.** Each glyph is re-lit, re-blurred, re-noised and perspective-warped to match the specific target image.
3. **Verification built in.** Every result is OCR-read back and quality-scored before the user accepts it.
4. **Learns from use.** Accepted/rejected results and manual corrections tune the profile.
5. **Private and free.** Runs locally with free, open-source models. Images never leave the machine.

---

## 4. Target users

| Persona | Description | Primary need |
|---------|-------------|--------------|
| **Owner-operator (primary)** — Xavier Sun | Does token replacement as a recurring job; has many real sample images of the same token font. Moderate technical skill, not a professional retoucher. | Fast, natural-looking, repeatable replacements with minimal manual work. |
| **University evaluator (secondary)** | Professors/peers viewing the showcase. | Understand the pipeline, see before/after quality, see measurable results. |

Assumption **A-01:** MVP is single-user on one Windows PC. Multi-user is out of scope (§17).

---

## 5. Glossary

| Term | Meaning |
|------|---------|
| **Token** | The short printed string to be replaced (letters, digits, separators). |
| **Target image** | The image containing the existing token that will be replaced. |
| **Style Profile** ("profile") | A trained style for one token design: its glyph bank, character set, token pattern, layout rules and learned adjustments. |
| **Reference image** | A real image of the same token design uploaded to train a profile. |
| **Glyph** | One extracted real character sample (e.g. a specific "7") stored with a soft transparency mask and metadata (size, stroke, blur, ink colour, lighting). |
| **Glyph bank** | All glyphs in a profile. |
| **Coverage** | Which characters of the profile's character set have enough good glyphs. |
| **Edit job** | One replacement: target image → detected token → new token → result. |
| **Batch** | One target image used as a template + a list of new token values → many results. |
| **Quality report** | Automatic checks on a result: OCR read-back, seam visibility, noise/sharpness/colour consistency. |

---

## 6. Core user journeys

### J1 — First run
1. Owner launches Traid.
2. Traid checks that the AI models are present and shows engine status (CPU/GPU).
3. Owner creates the local owner account (username + password) and acknowledges the Acceptable Use notice (§10, rule 6).
4. Owner lands on Home with an empty state that points to "Create your first Style Profile".

### J2 — Train a Style Profile
1. Owner creates a profile: name, character set (default `0–9 A–Z -`), optional token pattern (e.g. `^[A-Z]\d-\d{6}$`).
2. Owner drags in many reference images (different angles, lighting, textures).
3. Traid detects text in every image, segments individual characters, and extracts each as a glyph with a soft mask.
4. Owner opens the **Glyph Review** grid: glyphs are grouped by character; low-confidence ones are flagged. Owner confirms, relabels or rejects with keyboard shortcuts.
5. Coverage view shows every character's sample count and quality. Missing characters are highlighted with "add images containing: Q, X".
6. Profile becomes **Ready** when every character in the set has ≥ 3 confirmed glyphs (configurable).

### J3 — Replace a token (core loop)
1. Owner drops a target image on Home or the Editor and picks a profile (last used is preselected).
2. Traid detects all text, then auto-selects the most likely token region (pattern match + learned typical position + style similarity). The detected old text is shown.
3. Owner confirms or picks a different region; can drag the 4 corner handles to correct the region.
4. Owner types the new token. Input is validated against the profile's character set and pattern.
5. Traid generates the result: removes the old text, reprints the new token with matched glyphs, harmonizes appearance, runs the quality report.
6. Owner reviews: before/after slider, 100%–800% zoom, mask overlay toggle, quality report.
7. Optional fine-tuning: nudge position, scale, letter spacing, stroke weight, blur, ink tone, grain; swap an individual character to another glyph variant. Each change re-renders the result.
8. Owner **Accepts** (result saved, learning updated) or **Rejects** with an optional reason.
9. Owner exports the result in the same format and resolution as the input.

### J4 — Batch replace
1. From an accepted edit (or a target image with a confirmed region), owner chooses "Batch".
2. Owner pastes or imports (CSV/TXT, one per line) a list of new token values.
3. Traid validates every value, shows invalid ones, and runs the batch with progress.
4. Results grid: each item shows thumbnail, value, quality status. Items with warnings are surfaced first.
5. Owner reviews flagged items (same review tools as J3), accepts/rejects, then exports all accepted results as a ZIP with predictable file names.

### J5 — Review history
1. Owner opens History: list of all edit jobs (filter by profile, status, date; search by token value).
2. Opens a job to see before/after, parameters used, quality report and audit entries. Can re-export or re-open in the Editor.

### J6 — Improve a profile over time
1. Every accepted edit increases the usage/acceptance score of the glyphs used; rejected ones decrease.
2. Real (unedited) characters found in target images can be offered as new glyph candidates for the bank (owner confirms).
3. Owner's repeated manual adjustments (e.g. always +0.3 blur) become the profile's learned defaults.
4. Profile page shows learning stats: acceptance rate trend, most-rejected glyphs, coverage gaps.

---

## 7. User stories

Priority: **M** = Must (MVP), **S** = Should (MVP if time allows, planned), **C** = Could (post-MVP).

### Account & system
| ID | Story | Pri | Acceptance criteria |
|----|-------|-----|---------------------|
| US-01 | As the owner, I create a local account on first run so my work is protected on a shared PC. | M | Setup is only available while no user exists; password ≥ 10 chars; Acceptable Use must be acknowledged. |
| US-02 | As the owner, I sign in and out; my session expires after inactivity. | M | Wrong credentials show a generic error; 5 failed attempts → 5-minute lockout; idle expiry default 12 h. |
| US-03 | As the owner, I see whether the engine runs on CPU or GPU and whether models are installed. | M | Settings → Engine shows model names, versions, status, device. Missing model → clear fix instructions. |

### Style Profiles
| ID | Story | Pri | Acceptance criteria |
|----|-------|-----|---------------------|
| US-10 | Create, rename, describe and archive a profile. | M | Name unique (1–60 chars); archived profiles hidden by default and restorable. |
| US-11 | Upload many reference images at once (drag & drop). | M | Accepts JPEG/PNG/TIFF up to 50 MB / 40 MP each; duplicates (same file hash) are skipped with a notice. |
| US-12 | Traid extracts glyphs automatically from references. | M | Progress shown per image; failures listed with reason; extraction runs in background and survives navigation. |
| US-13 | Review glyphs: confirm, relabel, reject, in bulk, by keyboard. | M | Grid grouped by character; filter by status/quality; multi-select; shortcuts documented in DESIGN.md. |
| US-14 | See character coverage and what is missing. | M | Matrix of characters with counts and quality; "Ready" rule visible. |
| US-15 | Optionally provide the known text of a reference image to improve labels. | S | When provided, labels come from known text alignment instead of OCR guess. |
| US-16 | Set layout rules: alignment, spacing mode, token pattern. | M | Defaults: alignment auto, spacing auto, no pattern. |

### Editing
| ID | Story | Pri | Acceptance criteria |
|----|-------|-----|---------------------|
| US-20 | Drop a target image and have text detected automatically. | M | All text regions drawn as overlays with recognized text and confidence. |
| US-21 | Have the token region auto-selected. | M | Best candidate preselected and explained ("matches pattern", "usual position"); owner can change. |
| US-22 | Adjust the region with 4 corner handles. | M | Handles draggable at any zoom; arrow keys nudge 1 px (Shift = 10 px). |
| US-23 | Type the new token with validation. | M | Characters outside profile set rejected inline; pattern mismatch shows warning (not hard block unless pattern is marked strict). |
| US-24 | Generate a natural-looking replacement. | M | Output same pixel size, format, DPI and ICC profile as input; only pixels inside the edit mask (+ feather) change. |
| US-25 | See a quality report on every result. | M | OCR read-back equals new token (else warning); seam, noise, sharpness, colour checks with pass/warn. |
| US-26 | Compare before/after and inspect at pixel level. | M | Split slider, toggle (`\`), zoom 10%–800%, pan, mask overlay. |
| US-27 | Fine-tune the result with simple controls. | M | Position, scale, spacing, weight, blur, ink tone, grain; each re-renders in ≤ 3 s on reference hardware (§9). |
| US-28 | Swap one character to another glyph variant. | S | Click a character → shows top 6 alternative glyphs → pick one → re-render. |
| US-29 | Accept or reject a result with an optional reason. | M | Accept stores result and updates learning; reject keeps record with reason. |
| US-30 | Export the accepted result. | M | Same format as input by default; filename pattern configurable; JPEG quality matched to source estimate. |
| US-31 | Undo/redo adjustments within an edit session. | S | At least 30 steps. |

### Batch
| ID | Story | Pri | Acceptance criteria |
|----|-------|-----|---------------------|
| US-40 | Paste or import a list of token values for one template. | S | Max 1,000 values per batch; invalid values listed with reasons before start. |
| US-41 | Run the batch in the background with progress and cancel. | S | Progress count, ETA, cancel keeps finished items. |
| US-42 | Review items with warnings first, accept/reject. | S | Default sort: warnings first. |
| US-43 | Export all accepted items as a ZIP. | S | File names from pattern, e.g. `{template}_{token}.jpg`; collisions suffixed. |

### History, learning, settings
| ID | Story | Pri | Acceptance criteria |
|----|-------|-----|---------------------|
| US-50 | Browse and search history. | M | Filter by profile/status/date; search by old or new token; paginated. |
| US-51 | Re-open a past job in the Editor. | S | Opens with same region and parameters. |
| US-52 | See learning stats for a profile. | S | Acceptance rate, top rejected glyphs, coverage gaps. |
| US-53 | Add real characters from target images to the glyph bank. | S | Offered after accept; owner confirms each. Only original (unedited) pixels are ever used. |
| US-54 | Create and restore a backup of all data. | S | One-click backup to ZIP; documented restore procedure. |
| US-55 | Change password and export defaults. | M | — |
| US-56 | See who built the app. | M | "Designed & developed by Xavier Sun" visible in the app shell, sign-in screen and About. |

---

## 8. Features & functional requirements

### 8.1 Engine pipeline (backend)

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-E01 | **Text detection & recognition** on any input image using a free, local OCR model (PP-OCR family via ONNX Runtime). Output: list of regions, each with a 4-point quad, recognized string, confidence. | M |
| FR-E02 | **Token candidate scoring**: rank regions by (a) profile token-pattern match, (b) similarity of position to the profile's learned typical region, (c) style similarity to the profile's glyphs, (d) OCR confidence. | M |
| FR-E03 | **Rectification**: warp the selected quad to a frontal, axis-aligned crop via homography; keep the inverse transform for re-projection. | M |
| FR-E04 | **Character segmentation** inside the rectified crop: adaptive binarization + connected components, guided by OCR character count/positions; outputs per-character boxes, baseline, cap height, pitch. | M |
| FR-E05 | **Soft glyph mask (alpha) extraction**: estimate local background and ink colour; compute per-pixel ink coverage so anti-aliased edges and ink texture are preserved. | M |
| FR-E06 | **Text removal**: build a removal mask from the old glyph masks (dilated); fill with a free inpainting model (LaMa via ONNX Runtime). Fallback to classical inpainting (OpenCV) if the model is unavailable or region is tiny. | M |
| FR-E07 | **Glyph selection** per new character, in priority order: (1) the same character already present in *this* image's original token or nearby same-style text, (2) best-matching glyph from the profile bank by condition similarity (size, stroke, blur, lighting, angle) weighted by learned acceptance score, (3) if no glyph exists → block with a coverage error (never fall back to a system font). | M |
| FR-E08 | **Layout**: if new token has the same length as old → reuse each original character slot exactly. Otherwise use profile alignment (left/center/right/auto) and spacing (monospace pitch or learned proportional advances), anchored to the original baseline. | M |
| FR-E09 | **Appearance harmonization**: scale to cap height; transfer local illumination (shading ratio from inpainted background); match ink colour from original glyph pixels; match blur (estimated from original edge profile); match noise/grain level; apply re-projection with the inverse homography. | M |
| FR-E10 | **Compositing**: alpha-composite into the inpainted image with a feathered boundary; only pixels inside mask + feather may change. | M |
| FR-E11 | **Output encoding**: same format, dimensions, DPI and ICC profile as input. JPEG output re-encoded at the estimated source quality so compression texture is uniform. Exports carry a Traid edit marker in metadata unless the owner disables it (see D-06). Original camera EXIF is **not** copied into exports. | M |
| FR-E12 | **Quality report**: (a) OCR read-back of the result region must equal the new token; (b) seam score along mask boundary; (c) noise σ, sharpness and colour statistics inside vs. surrounding ring; each → pass / warn with numeric value. | M |
| FR-E13 | **Determinism**: same input + parameters + engine version + seed → identical output. | M |
| FR-E14 | **Engine interface** is swappable so a future generative engine (Phase 2) can be added without changing the API or UI. | M |

### 8.2 Profiles & learning

| ID | Requirement | Pri |
|----|-------------|-----|
| FR-P01 | CRUD + archive for profiles; fields per DATABASE.md. | M |
| FR-P02 | Reference upload (multi-file), dedupe by SHA-256, background extraction, per-image status. | M |
| FR-P03 | Glyph review: confirm, relabel, reject, bulk actions; only `confirmed` (and, if owner allows, high-confidence `auto`) glyphs are used for rendering. | M |
| FR-P04 | Coverage computation and Ready rule (≥ 3 confirmed glyphs per character, configurable 1–20). | M |
| FR-P05 | Learning signals: per-glyph use/accept/reject counts; profile-level learned default adjustments (running average of owner adjustments on accepted jobs); learned typical token region. | M |
| FR-P06 | Glyph candidates from target images (original pixels only) offered after accept. Never harvest glyphs from generated output. | S |

### 8.3 Editor, batch, history, settings
| ID | Requirement | Pri |
|----|-------------|-----|
| FR-U01 | Editor implementing J3 with all review and fine-tune controls (US-20…US-31). | M |
| FR-U02 | Batch implementing J4 (US-40…US-43). | S |
| FR-U03 | History list + job detail (US-50, US-51). | M |
| FR-U04 | Settings: account, engine status, export defaults (format, filename pattern, metadata marker), storage location and usage, backup, About/credits. | M |
| FR-U05 | Audit log of security- and output-relevant actions (sign-in, failed sign-in, accept, reject, export, delete, settings change, backup). Viewable in Settings. | M |
| FR-U06 | All long operations run as background tasks with progress, and the UI stays responsive. | M |

---

## 9. Non-functional requirements

| Area | Requirement |
|------|-------------|
| **Platform** | Windows 10/11 x64 (primary). The UI runs in a modern Chromium-based browser or Firefox against a local server on `127.0.0.1`. |
| **Reference hardware** (Assumption **A-02**, confirm in D-09) | 4+ core CPU, 16 GB RAM, optional NVIDIA/AMD/Intel GPU. GPU is optional; CPU must be fully supported. |
| **Performance (CPU)** | Detection ≤ 4 s on a 12 MP image; full render ≤ 10 s; re-render after an adjustment ≤ 3 s (cached removal & detection); glyph extraction ≤ 3 s per reference image. |
| **Performance (GPU)** | Full render ≤ 4 s. |
| **Batch throughput** | ≥ 6 results/minute on CPU for same-template batches (removal reused across items). |
| **Quality** | Unchanged pixels outside mask+feather: bit-identical for PNG/TIFF. OCR read-back accuracy ≥ 98% on the evaluation set. See §18 for blind-test target. |
| **Privacy** | 100% local processing. No telemetry, analytics or cloud calls at runtime. Network is used only to download model files during setup (checksums verified). |
| **Security** | Server binds to `127.0.0.1` only; password hashed with Argon2id; sessions via HttpOnly cookie; CSRF protection; upload validation; no secrets in the frontend. |
| **Reliability** | Background tasks persisted; an app restart marks interrupted tasks as failed with a retry option; no data loss on crash (SQLite WAL). |
| **Usability** | Core journey J3 achievable in ≤ 5 interactions after image drop (select profile → confirm region → type token → generate → accept). Every editor action has a keyboard shortcut. |
| **Accessibility** | WCAG 2.2 AA for all non-canvas UI; canvas content mirrored in accessible lists. |
| **Maintainability** | Typed code (Python type hints + mypy, TypeScript strict); engine stages unit-tested with fixture images; documented in repo. |
| **Storage** | Data folder configurable; app shows disk usage; images stored once (content-addressed). |
| **Offline** | Fully functional offline after setup. |

---

## 10. Product rules & constraints

1. **No system-font fallback.** If a required character has no glyph, the render is blocked with a clear coverage message.
2. **No changes outside the mask.** The engine never modifies pixels outside the edit mask + feather band.
3. **Generated output is never training data.** Only original, real pixels feed the glyph bank.
4. **Every output is auditable.** Accept/export always writes an audit entry linking input, output, old and new token.
5. **Original files are never overwritten.** Inputs are stored read-only; outputs are new files.
6. **Acceptable use.** On first run (and in About) the owner acknowledges that Traid must only be used on documents/images they own or are authorized to produce and edit, and must not be used to alter identity documents, currency, financial instruments, official certificates or third-party documents. Traid includes no anti-forensic features (no EXIF spoofing, no metadata forging).

---

## 11. Pages / screens

| # | Screen | Purpose | Key contents |
|---|--------|---------|--------------|
| S1 | **Setup** (first run only) | Create owner account, accept Acceptable Use, check engine. | Engine check list, account form, AUP checkbox. |
| S2 | **Sign in** | Authenticate. | Username, password, credit line. |
| S3 | **Home** | Start work fast. | Drop zone ("Drop a target image"), profile picker, recent jobs, profile readiness summary. |
| S4 | **Profiles** | List profiles. | Cards/rows: name, status, glyph count, coverage %, last used. Create button. |
| S5 | **Profile detail** | Manage one profile. | Tabs: Overview (stats, learning), References (upload, per-image status), Glyphs (review grid), Coverage (matrix), Settings (charset, pattern, layout, thresholds). |
| S6 | **Editor** | Core replacement workflow. | Canvas (zoom/pan, overlays, before/after), left panel (regions list), right inspector (token input, generate, adjustments, quality report, accept/reject/export). |
| S7 | **Batch** | Many tokens, one template. | Value input/import, validation list, progress, results grid, review drawer, export. |
| S8 | **History** | Find past work. | Filterable table; job detail view. |
| S9 | **Settings** | Configuration. | Account, Engine, Export, Storage & Backup, Audit log, About (credits). |
| S10 | **Not found / Forbidden / Session expired** | System states. | Clear message + way back. |

---

## 12. Roles & permissions

MVP has one role. The data model keeps a `role` field so a second role can be added without migration of existing data.

| Capability | Owner (MVP) | Editor (Phase 2, not built) |
|------------|:-----------:|:---------------------------:|
| Sign in / out, change own password | ✅ | ✅ |
| Create / edit / archive profiles | ✅ | ❌ |
| Upload references, review glyphs | ✅ | ✅ |
| Run edits & batches, accept / reject / export | ✅ | ✅ |
| View history | ✅ (all) | Own jobs only |
| Delete jobs / profiles permanently | ✅ | ❌ |
| Settings, backup, audit log | ✅ | ❌ |
| Manage users | ❌ (not in MVP) | ❌ |

All checks are enforced server-side.

---

## 13. Data requirements

Detailed schema lives in DATABASE.md. The product needs to persist:

| Entity | Key data | Retention |
|--------|----------|-----------|
| User | username, password hash, role, lockout state | Until deleted |
| Session | hashed token, expiry | Purged after expiry |
| Style Profile | name, charset, pattern, layout rules, thresholds, learned params, typical region | Until permanently deleted |
| Reference image | file, known text, extraction status, estimated capture conditions | With profile |
| Glyph | character, soft-mask crop, metrics, quality, status, learning counters, source | With profile |
| Edit job | input/result/mask files, regions, old/new text, parameters, quality report, status, engine version, seed | Until deleted by owner |
| Batch | template job, values, status, export ZIP | Until deleted |
| Task | type, status, progress, error | 30 days |
| Audit event | actor, action, subject, timestamp, non-sensitive details | Kept (append-only) |
| Settings | export defaults, thresholds, metadata marker toggle | — |

Sensitive data: token values and images are treated as confidential business data — stored locally only, never logged in plain application logs, never sent anywhere.

---

## 14. Integrations

| Integration | Purpose | Type | MVP |
|-------------|---------|------|-----|
| PP-OCR models (detection + recognition) via ONNX Runtime | Find and read text | Local open-source model | ✅ |
| LaMa inpainting model via ONNX Runtime | Remove old text | Local open-source model | ✅ |
| OpenCV | Geometry, binarization, classical inpainting fallback, blending | Local library | ✅ |
| Model download (official release URLs, pinned, checksum-verified) | One-time setup | Setup script only | ✅ |
| Cloud AI APIs | — | Not used (privacy, cost, reliability) | ❌ |
| Generative scene-text model (e.g. diffusion fine-tuned on own data) | Phase 2 "AI Engine v2" | Local, GPU | ❌ |

No webhooks, payments, email or third-party accounts.

---

## 15. Loading, empty and error states

| Context | Loading | Empty | Error |
|---------|---------|-------|-------|
| App start | Splash with engine check progress | — | Model missing → "Run setup" instructions; port busy → message with alternative port |
| Home | Skeleton for recent jobs | "No edits yet. Create a Style Profile, then drop a target image." | Recent jobs failed to load → inline retry |
| Profiles list | Skeleton rows | "No profiles yet" + Create | Inline retry |
| References upload | Per-file progress, then "Extracting glyphs n/N" | "Drop real images of this token design. Different angles and lighting help." | Per-file: unsupported format, too large, unreadable, no text found |
| Glyph review | Skeleton grid | "No glyphs yet — upload references" | Load failure → retry |
| Coverage | — | All characters shown as 0 | — |
| Editor: detection | Overlay "Detecting text…" with progress | "No text found" → draw region manually option | Detection failed → retry / manual region |
| Editor: profile not ready | — | Banner: "Missing glyphs for: Q, 7" + link to Coverage | Generate disabled with reason |
| Editor: render | Progress steps: Removing → Placing → Matching → Checking | — | Render failed → error code + retry; partial results never shown as final |
| Quality report | Spinner in report panel | — | Any check warns → amber state with explanation; result still reviewable |
| Batch | Progress bar, count, ETA | "Add token values to start" | Item failures listed; batch continues; summary at end |
| History | Skeleton table | "No jobs match these filters" + clear filters | Retry |
| Export | Button spinner | — | Disk full / permission → message with path |
| Session | — | — | Expired → redirect to Sign in, return to the same page after login |
| Server unreachable | — | — | Full-width banner "Traid engine is not running" + retry |

---

## 16. MVP scope

**In MVP (Must):** J1, J2, J3, J5; US marked **M**; FR-E01…E14, FR-P01…P05, FR-U01, FR-U03…U06; local owner account; audit log; export with metadata marker; dark UI.

**MVP if time allows (Should):** Batch (J4), glyph variant swap, undo/redo, known-text labels, glyph candidates from targets, learning stats view, backup/restore.

## 17. Out of scope (MVP)

- General photo editing (crop, filters, layers, brushes, retouching beyond the token region).
- Fonts the owner has not trained (no generic font rendering).
- Handwriting, non-Latin scripts, lowercase (unless approved in D-07), curved/circular text.
- Generative AI engine / model fine-tuning / synthetic dataset generation (Phase 2).
- Multiple users, roles beyond Owner, cloud sync, hosting, mobile apps.
- PDF/vector input (raster images only).
- Video.
- Any feature intended to defeat forensic detection or forge metadata.

## 18. Success criteria

| Metric | Target | How measured |
|--------|--------|--------------|
| OCR read-back correctness | ≥ 98% of results | Quality report over evaluation set (≥ 100 edits) |
| Visual naturalness (blind test) | Viewers identify the edited image in a real-vs-edited pair at ≤ 60% accuracy (50% = chance) | Evaluation kit: 20+ pairs shown to ≥ 10 viewers at showcase |
| Acceptance rate | ≥ 80% of first renders accepted without fine-tuning, on a Ready profile | App learning stats |
| Time per token | ≤ 60 s from drop to export (vs. manual retouching, typically 10+ min) | Timed sessions |
| Learning effect | Acceptance rate after 50 accepted edits ≥ acceptance rate of first 10 + 10 pts | App learning stats |
| Stability | Zero crashes and zero data loss across the evaluation set | Logs, task table |

---

## 19. Assumptions

| ID | Assumption |
|----|-----------|
| A-01 | Single owner, single Windows PC. |
| A-02 | Mid-range laptop/desktop; GPU optional. |
| A-03 | Tokens are short (≤ 24 chars), single-line, printed (not handwritten), mostly flat or gently angled surfaces. |
| A-04 | Owner can supply ≥ 30 real reference images per token design, covering every character at least 3 times. |
| A-05 | Owner is authorized to produce and edit the documents/images involved (their own job materials). |
| A-06 | Input is photos or scans in JPEG/PNG/TIFF (8-bit). |
| A-07 | One profile = one font/print design. Different designs = different profiles. |

## 20. Decisions requiring owner approval

**Status: all decisions D-01…D-10 APPROVED as recommended by the owner on 2026-10-20.** D-09 hardware details are still to be provided; performance targets stay provisional until then.

| ID | Decision | Recommendation (approved) |
|----|----------|----------------|
| D-01 | Product name "Traid" (from folder "Traid by SUN"). | Approve or rename. |
| D-02 | Platform: local web app (browser UI + local Python engine) vs. packaged desktop app. | Local web app for MVP; desktop installer wrapper later. |
| D-03 | Require sign-in for a local single-user app. | Yes (protects data on shared PCs; required for audit trail). |
| D-04 | MVP engine = real-glyph transplant + classical/AI harmonization; generative AI engine deferred to Phase 2. | Approve. It is more reliable for a single known font and runs on CPU. |
| D-05 | Batch mode in MVP as "Should". | Approve. |
| D-06 | Exports carry an invisible Traid edit marker in file metadata (on by default, owner-switchable) + audit log always on. | Approve. |
| D-07 | Character set: `0–9`, `A–Z`, `-`, `/`, `#`, space. Lowercase? | Approve set; tell us if lowercase is needed. |
| D-08 | Dark-only UI in MVP (neutral grey for accurate image judgement). | Approve. |
| D-09 | Reference hardware: share your PC's CPU, RAM and GPU. | Needed to confirm performance targets. |
| D-10 | Input formats JPEG/PNG/TIFF; max 50 MB / 40 MP. | Approve. |

## 21. Open questions

1. What kind of document carries the tokens (e.g. queue slips, event passes, product labels)? This affects defaults (pattern, layout, typical texture).
2. Are target images mostly phone photos or flatbed scans?
3. Roughly how many reference images exist today, and do they cover every character?
4. Is the token always in the same position on the page (template-like) or anywhere?
5. What is the university showcase date? It drives which "Should" items are realistic.
