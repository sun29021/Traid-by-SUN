# AGENTS.md — Rules for coding agents working on Traid

Project owner: **Xavier Sun**. These rules apply to every change, by any agent or human, for the whole life of the project.

## 0. Source of truth

Read before working. Order of precedence when they disagree:

1. **PRD.md** — what to build, scope, acceptance criteria
2. **ARCHITECTURE.md** — how it is built (stack, layers, folders, security)
3. **DATABASE.md** — data model
4. **API.md** — HTTP contract
5. **DESIGN.md** — visual and UX rules
6. **IMPLEMENTATION_PLAN.md** — order of work

If a task conflicts with these documents, **stop and ask** the owner. Do not silently change requirements. If you change behavior that a document describes, update that document in the same change.

## 1. Working method (every task)

1. **Inspect first.** Read the relevant existing code, tests and docs before editing. Search for an existing component, utility, schema or pattern before creating a new one.
2. **Plan briefly.** State the approach in 2–5 lines and the files you expect to touch.
3. **Change only what the task needs.** No unrelated refactors, renames, formatting sweeps or "while I'm here" fixes. Note unrelated issues in your report instead.
4. **Keep it runnable.** After every task, the app starts, and `scripts/check` passes.
5. **Verify.** Run the relevant tests and the type checkers. Do not claim something works without running it.
6. **Report:** files changed, tests run (with results), anything not done, decisions needing approval.

## 2. Code quality & naming

- Readable over clever. Small functions with one job. No dead code, commented-out code or TODOs without an owner note (`TODO(owner-approval): …`).
- **Python:** PEP 8 via ruff; `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants; modules named for what they contain (`glyph_select.py`, not `utils2.py`).
- **TypeScript/React:** `PascalCase` components and their files (`TokenInput.tsx`), `camelCase` functions/variables, hooks start with `use`, CSS Modules named `Component.module.css`.
- Domain words are fixed and used everywhere exactly as in PRD §5: *token, target image, profile (Style Profile), reference image, glyph, glyph bank, coverage, edit job, batch, quality report*. Do not introduce synonyms.
- Comments explain *why*, not *what*. Engine algorithms get a short docstring describing the technique and its inputs/outputs (units: pixels, σ, 0–1).

## 3. Project & folder structure

- Follow ARCHITECTURE.md §11 exactly. New top-level folders require owner approval.
- Backend layer rules (ARCHITECTURE.md §3.1) are mandatory:
  - `api/` → `services/` → `repositories/` / `storage/` / `worker`; `engine/` is pure and imports nothing from the app.
  - Routers contain no business logic and no DB queries.
  - Services own transactions and audit writes.
- Frontend: `components/` (design-system primitives) never import from `features/`. All HTTP goes through `lib/api`.
- One concept per file. Tests mirror source paths (`app/engine/segment.py` → `tests/unit/engine/test_segment.py`).

## 4. Component & code reuse

- UI must be built from `frontend/src/components` primitives. If a primitive is missing, add it there (with states from DESIGN.md §6 and a test), then use it.
- Styling uses only the tokens in `styles/tokens.css` (DESIGN.md). **No hard-coded colours, font sizes, spacing or radii** in components. No inline styles except computed canvas/overlay geometry.
- Do not duplicate Pydantic schemas, enums or error codes — import them. Frontend API types are generated from OpenAPI; do not hand-write duplicates.
- Reuse engine stages; do not re-implement homography, matting or I/O in another module.

## 5. Dependency management

- Allowed dependencies are those listed in ARCHITECTURE.md §2. Adding any other runtime dependency requires: a reason, why existing deps can't do it, its license (must be permissive/compatible), and owner approval.
- Pin via lock files (`uv.lock`, `package-lock.json`); commit lock files. Use `uv add` / `npm install --save-exact`.
- Never add: cloud SDKs, telemetry/analytics, CSS frameworks or UI kits, state-management libraries, PyTorch (until Phase 2 is approved), anything that phones home.
- Model files are listed in `models/manifest.json` with SHA-256 and license; never commit `.onnx` files.

## 6. Type safety

- Python: full type hints; `mypy --strict` must pass for `backend/app`. No `Any` except at true boundaries (with a comment). Use dataclasses/Pydantic models, not loose dicts, for engine and service data. NumPy arrays annotated with `numpy.typing.NDArray[...]`.
- TypeScript: `strict: true`, `noUncheckedIndexedAccess: true`. No `any`, no `@ts-ignore` (use `@ts-expect-error` with a reason only in tests). Validate untrusted data (forms, URL params) with Zod.
- JSON columns are read/written only through Pydantic models.

## 7. Error handling

- Raise typed `AppError` subclasses with codes from API.md §1.3. Adding a code means updating API.md.
- Never swallow exceptions. Never `except Exception: pass`. Catch narrowly; log with request/task ID; convert to an error code.
- Engine fallbacks (e.g. OpenCV inpaint) must be reported in the quality report, never silent.
- Frontend: every data view implements loading, empty, error and success states per DESIGN.md §9. Show the API error code in small mono text.
- Never show stack traces to the user.

## 8. Security & secrets

- **Never commit secrets** or `.env`. Only `.env.example` with placeholder/default values.
- Never expose anything secret to the frontend; `VITE_` variables are public by definition.
- Enforce authentication and authorization **server-side** on every endpoint (API.md §1.6). Frontend guards are UX only.
- Ownership: every repository query on owned data is scoped by `owner_id`. Foreign resources return 404.
- State-changing endpoints require the CSRF header. Cookies stay HttpOnly + SameSite=Strict.
- Server binds to `127.0.0.1` only; do not change without owner approval.
- Uploads: validate size, magic bytes, full decode, pixel limit. Never use client filenames as paths.
- Never log passwords, session tokens, CSRF secrets, token values (old/new text) or image content.
- No shell execution from request data. No `eval`, no dynamic imports from user input. User-provided regex is validated and length-limited.
- Respect product rules (PRD §10): no system-font fallback, no pixel changes outside the mask, generated output never becomes training data, no EXIF/metadata spoofing or anti-forensic features. Requests to add such features must be refused and raised with the owner.

## 9. Database & API access

- Schema changes only through Alembic migrations that match DATABASE.md; update DATABASE.md in the same change. No destructive migration without owner approval.
- ORM only; no string-built SQL. Use transactions for multi-row changes.
- Follow API.md exactly: paths, envelopes, status codes, error codes, pagination. Contract changes update API.md and the generated frontend types in the same change.
- Heavy work (anything calling the engine) runs in the worker via tasks, never inside a request handler.
- Do not store binaries in the DB; use `storage/` and the `files` table.

## 10. Testing

- Every change ships with tests at the right level (ARCHITECTURE.md §15):
  - Engine stage → unit test with synthetic fixtures (ground truth known).
  - Service rule / state transition → service test.
  - Endpoint → integration test incl. auth (401), CSRF (403), foreign ownership (404) and validation (422).
  - UI primitive or complex component → Vitest test; core journeys → Playwright.
- Bug fixes start with a failing test that reproduces the bug.
- Never delete, skip or weaken a test to make a change pass. Never change production behavior only to satisfy a test.
- Tests are deterministic (fixed seeds, no network, temp data dirs). Model-dependent tests use `@pytest.mark.models`.
- `scripts/check` (ruff, mypy, pytest, eslint, tsc, vitest) must pass before a task is reported done.

## 11. Documentation

- Update the relevant `.md` source-of-truth file whenever behavior, schema, API, design tokens or architecture change.
- README.md stays accurate for: prerequisites, setup, run, test, backup/restore.
- New env variables → `.env.example` + ARCHITECTURE.md §12 + API.md §7.
- Public functions in `engine/` and `services/` have docstrings.
- Credit "Designed & developed by Xavier Sun" must remain where DESIGN.md §14 requires; never remove it.

## 12. Git & change discipline

- Default branch `main` is always runnable. Work on short-lived branches: `feat/<phase>-<topic>`, `fix/<topic>`, `chore/<topic>`, `docs/<topic>`.
- Small, focused commits; message format `type(scope): summary` (e.g. `feat(engine): add soft glyph matting`), body explains why.
- One logical change per commit/PR; no mixing refactors with features.
- Never force-push `main`, rewrite shared history, or commit generated artefacts (`dist/`, `data/`, `.venv/`, `node_modules/`, `*.onnx`).
- Do not commit or push unless the owner asks.
- Before finishing: review your own diff for unrelated changes, debug prints, secrets and leftover files.

## 13. When to stop and ask

Stop and ask the owner when:
- A requirement is ambiguous and the choice changes behavior or data.
- A task needs a new dependency, folder, service, env variable with a secret, or schema change not in the docs.
- A change would weaken security, privacy, or a product rule in PRD §10.
- Tests reveal behavior that contradicts the documents.
- Something listed in PRD §20 (decisions requiring approval) is still unresolved and blocks the task.
