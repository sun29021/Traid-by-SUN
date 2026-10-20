# DESIGN — Traid

**Owner:** Xavier Sun
**Status:** Draft v1.0
**Derives from:** PRD.md (product source of truth)
**Scope:** All visual design and UX rules for the Traid UI. Components and pages must be built from the rules here; no one-off styling.

---

## 1. Visual direction

**"Darkroom proof desk."** Traid is a precision instrument for judging tiny printed details. The UI behaves like a retoucher's workspace: quiet, neutral, dense, and out of the way of the image.

What this means in practice:
- **The image is the brightest, most colourful thing on screen.** UI chrome is neutral grey with no colour tint, so the eye judges ink colour and paper tone correctly.
- **Proof-mark accent.** One warm accent (amber, like a proofreader's marker) is used for the current selection and the single primary action. Nothing else is decorated.
- **Engineering honesty.** Numbers (confidence, blur σ, seam score) are shown, in monospace, next to plain-language labels. The user sees *why* the result is good or not.
- **Flat surfaces, hairline borders.** Depth comes from 1 px borders and surface steps, not shadows, gradients or glass.

What to avoid (explicitly banned):
- Gradient backgrounds, glowing blobs, glassmorphism, neon.
- Large marketing-style hero sections, illustrations, emoji in UI.
- Rounded "bubbly" cards with big shadows; cards inside cards.
- Coloured or tinted greys behind images.
- Generic SaaS dashboards full of vanity charts.

## 2. Design principles

1. **Image first.** Canvas gets maximum area; panels are collapsible; no chrome overlaps the image except intentional overlays.
2. **One obvious next step.** Each screen state has exactly one primary (amber) button.
3. **Show the evidence.** Every automatic decision (region choice, glyph choice, quality check) shows its reason and value.
4. **Reversible by default.** Adjustments are non-destructive and undoable; destructive actions confirm.
5. **Keyboard-complete.** Every editor action has a shortcut, shown in tooltips.
6. **Consistent density.** Compact, information-dense controls (32 px rows) everywhere; no mixing of airy and dense layouts.

---

## 3. Colour

All colours are defined as design tokens. Components reference tokens only, never raw values.

### 3.1 Neutral surfaces (true neutral, R=G=B)

| Token | Value | Use |
|-------|-------|-----|
| `--surface-0` | `#0E0E0E` | App background, canvas backdrop |
| `--surface-1` | `#161616` | Panels, sidebar |
| `--surface-2` | `#1E1E1E` | Inputs, list rows, raised controls |
| `--surface-3` | `#272727` | Hover state of surface-2, popovers, menus |
| `--surface-4` | `#323232` | Pressed/active state, selected row |
| `--border-subtle` | `#262626` | Dividers between panels |
| `--border-default` | `#353535` | Input and control borders |
| `--border-strong` | `#4A4A4A` | Focused-but-not-primary emphasis, table header line |

### 3.2 Text

| Token | Value | Contrast on surface-1 | Use |
|-------|-------|----------------------|-----|
| `--text-primary` | `#EDEDED` | 15.0:1 | Body, labels, values |
| `--text-secondary` | `#A3A3A3` | 7.4:1 | Helper text, metadata |
| `--text-tertiary` | `#8A8A8A` | 5.3:1 | Placeholders, disabled labels (min 4.5:1 kept) |
| `--text-on-accent` | `#1A1300` | 10.9:1 on accent | Text on amber buttons |

### 3.3 Accent and semantic

| Token | Value | Use |
|-------|-------|-----|
| `--accent` | `#F2B33D` | Primary button, current selection, active tab indicator, focus ring |
| `--accent-hover` | `#F6C462` | Primary hover |
| `--accent-pressed` | `#D99A22` | Primary pressed |
| `--accent-muted` | `#F2B33D29` (16% alpha) | Selected row tint, active nav item background |
| `--success` | `#4CC38A` | Quality check pass, "Ready" status |
| `--warning` | `#F08C2E` | Quality warn, "Needs review" (orange, deliberately distinct from the amber accent) |
| `--danger` | `#F0524F` | Errors, destructive actions, failed |
| `--info` | `#6AA8F0` | Neutral info banners, processing state |

Each semantic colour has a `-muted` variant at 16% alpha for backgrounds (e.g. `--danger-muted`).

Rule: **status is never colour alone.** Every status also has an icon and a text label.

### 3.4 Canvas overlay colours

Overlays sit on arbitrary photo content, so they use high-visibility colours with a 1 px dark outline (`#000000` at 60%) to stay visible on both light paper and dark backgrounds.

| Token | Value | Style | Meaning |
|-------|-------|-------|---------|
| `--ov-detected` | `#22D3EE` | 1.5 px dashed | Detected text region (not selected) |
| `--ov-selected` | `#F2B33D` | 2 px solid + corner handles | Selected token region |
| `--ov-mask` | `#FF3DAA` at 45% fill | Fill | Edit mask view |
| `--ov-glyph` | `#A78BFA` | 1 px solid | Per-character boxes (debug/inspect view) |
| `--ov-warning` | `#F08C2E` | 2 px dotted | Region flagged by quality check |

Line style differs per meaning (dashed / solid / dotted) so overlays remain distinguishable without colour.

### 3.5 Canvas backdrop
- Default backdrop is `--surface-0`.
- Optional backdrop toggle: mid-grey `#808080` and checkerboard (for viewing glyph alpha). Never coloured.

---

## 4. Typography

Fonts are bundled locally (app runs offline).

| Role | Family | Notes |
|------|--------|-------|
| UI | **IBM Plex Sans** (400, 500, 600) | Neutral, technical, excellent at small sizes |
| Data & tokens | **IBM Plex Mono** (400, 500) | Token values, numbers, metrics, file names, shortcuts. Tabular figures always. |

### Type scale (rem based on 16 px root; UI defaults to 13 px body for density)

| Token | Size / line-height | Weight | Use |
|-------|--------------------|--------|-----|
| `--type-display` | 24 / 32 | 600 | Page title (one per page) |
| `--type-title` | 18 / 24 | 600 | Section titles, dialog titles |
| `--type-heading` | 15 / 20 | 600 | Panel headers, card titles |
| `--type-body` | 13 / 20 | 400 | Default text, labels |
| `--type-body-strong` | 13 / 20 | 500 | Emphasised labels, table values |
| `--type-small` | 12 / 16 | 400 | Helper text, metadata, captions |
| `--type-micro` | 11 / 14 | 500, letter-spacing 0.04em, uppercase | Panel section labels only |
| `--type-mono` | 13 / 20 | 400 | Data values |
| `--type-token` | 20 / 28 mono | 500 | Token input field and token displays |

Rules:
- Sentence case everywhere ("Create profile", not "Create Profile"). Uppercase only for `--type-micro` section labels.
- Never below 11 px. Never more than 3 sizes on one panel.
- Numbers with units: value in mono, unit in sans secondary (`0.42` `σ`).

---

## 5. Spacing, sizing and layout

### 5.1 Spacing scale (4 px base)

| Token | px |
|-------|----|
| `--space-0` | 0 |
| `--space-1` | 4 |
| `--space-2` | 8 |
| `--space-3` | 12 |
| `--space-4` | 16 |
| `--space-5` | 24 |
| `--space-6` | 32 |
| `--space-7` | 48 |
| `--space-8` | 64 |

Rules: component internal padding uses 1–4; gaps between groups use 4–5; page margins use 5–6. No arbitrary values.

### 5.2 Sizes

| Token | Value | Use |
|-------|-------|-----|
| `--control-sm` | 24 px | Icon buttons in toolbars, chips |
| `--control-md` | 32 px | Default height for buttons, inputs, selects, list rows |
| `--control-lg` | 40 px | Primary actions in dialogs and auth screens, token input |
| `--radius-sm` | 4 px | Inputs, buttons, chips |
| `--radius-md` | 6 px | Panels, popovers, dialogs, thumbnails |
| `--radius-full` | 999 px | Status dots, toggles only |
| `--border-width` | 1 px | All borders |
| Icon size | 16 px (default), 20 px (nav rail) | Lucide icon set, 1.5 px stroke |

### 5.3 App shell layout

```
┌──────┬────────────────────────────────────────────────────────────┐
│      │  Top bar (48 px): page title · context actions · task chip │
│ Nav  ├────────────────────────────────────────────────────────────┤
│ rail │                                                            │
│ 64px │                     Page content                           │
│      │                                                            │
│ ···  │                                                            │
│ cred │                                                            │
└──────┴────────────────────────────────────────────────────────────┘
```

- **Nav rail (64 px)**: icon + 11 px label. Items: Home, Editor, Profiles, Batch, History, Settings. Bottom: engine status dot (CPU/GPU, ok/error), user menu, credit line "by Xavier Sun".
- **Top bar (48 px)**: page title (`--type-heading`), breadcrumbs on detail pages, page-level actions on the right, and the **Tasks chip** (shows running background tasks; click opens Tasks popover).
- **Content max width**: list/detail pages 1280 px centred with `--space-6` margins. Editor and Batch review are full-bleed.

### 5.4 Grid
- 12-column grid, 24 px gutters for list/detail pages.
- Panels in the Editor use fixed widths (see §11.5), not grid columns.

---

## 6. Reusable components

Each component lists its variants and required states. All interactive components have: default, hover, active/pressed, focus-visible, disabled. States not listed are not allowed.

### 6.1 Buttons
| Variant | Look | Use |
|---------|------|-----|
| `primary` | Amber fill, `--text-on-accent` | The single main action of a view |
| `secondary` | `--surface-2` fill, `--border-default` | Other actions |
| `ghost` | Transparent, text-primary; hover surface-3 | Toolbar and low-emphasis actions |
| `danger` | `--danger` text + border; fill on hover | Destructive actions (always confirmed) |
| `icon` | 24 or 32 px square, ghost style, requires tooltip + aria-label | Toolbars |

- Loading state: label stays, spinner replaces leading icon, button disabled, width fixed (no layout shift).
- Max one `primary` per view region (page, dialog, inspector).

### 6.2 Inputs
- **Text input / textarea**: 32 px, surface-2, border-default; focus = 1 px accent border + 2 px focus ring at 40% accent.
- **Token input**: 40 px, `--type-token` mono, letter-spacing 0.06em, live per-character validation (invalid characters underlined in danger with a tooltip). Shows character count and pattern status chip (`Pattern ✓` / `Pattern ✗`).
- **Number field with slider** (used by all adjustments): label left, value mono right, slider below; double-click value to type; double-click slider to reset to default; modified values show a small accent dot and "reset" icon.
- **Select / combobox**: native-like, keyboard searchable.
- **Checkbox, radio, toggle**: 16 px, accent when on.
- **File drop zone**: dashed border-default, on drag-over: accent border + accent-muted fill + "Release to upload".

### 6.3 Data display
- **Status badge**: dot + label, e.g. `● Ready` (success), `● Training` (info), `● Needs review` (warning), `● Failed` (danger), `● Draft` (neutral).
- **Metric row**: label (secondary) · value (mono) · unit · status icon. Used in Quality report and stats.
- **Table**: 32 px rows, sticky header, hairline row dividers, hover surface-2, selected surface-4 + 2 px accent left bar. Sortable headers show arrow. Row click opens detail; row actions in a trailing kebab menu.
- **Thumbnail**: radius-md, 1 px border-subtle, neutral backdrop; status badge overlay bottom-left.
- **Glyph tile**: 72 × 88 px; glyph on checkerboard; character label (mono) top-left; quality bar bottom; status border (confirmed = success 1 px, auto = none, rejected = danger dashed + 40% opacity). Selected = 2 px accent outline.
- **Coverage cell**: character (mono 18 px) + count; fill intensity by count (neutral greys), missing = danger outline + "0".
- **Progress**: linear bar (4 px) with step label; determinate when progress known, indeterminate otherwise.
- **Before/after slider**: vertical divider with 24 px handle; labels "Before" / "After" in micro type at top corners.

### 6.4 Containers
- **Panel**: surface-1, header (32 px, micro label + optional actions), collapsible sections with chevrons. Collapsed state remembered per user.
- **Dialog**: max 480 px (confirm) or 640 px (forms), radius-md, surface-1, border-default, scrim `#000` at 60%. Title, body, footer with actions right-aligned (primary rightmost).
- **Drawer**: right side, 420 px, used for Batch item review and History job detail on narrow screens.
- **Popover/menu**: surface-3, border-default, 4 px padding, 32 px items.
- **Toast**: bottom-right, surface-3, icon + message + optional action; auto-dismiss 5 s (errors persist until dismissed); max 3 stacked.
- **Banner**: full width inside page/panel; info/warning/danger; used for persistent states (profile not ready, engine offline).

### 6.5 Feedback
- **Tooltip**: 300 ms delay, surface-4, `--type-small`; includes shortcut in mono (`Toggle before/after  \`).
- **Inline field error**: danger text below field, icon, specific message.
- **Skeleton**: surface-2 blocks with 1.5 s subtle opacity pulse (disabled under reduced motion).

---

## 7. Navigation

- Primary navigation via the nav rail; current item: accent-muted background, accent 2 px left bar, label in text-primary.
- Detail pages use breadcrumbs in the top bar: `Profiles / Receipt Token A / Glyphs`.
- Profile detail uses **tabs** (underline style, accent 2 px indicator): Overview · References · Glyphs · Coverage · Settings. Tab state is in the URL.
- Editor is reachable from: Home drop zone, Editor nav item (opens empty editor with drop zone), History "Open in editor", Profile "Test this profile".
- **Global shortcuts**: `G H` Home, `G E` Editor, `G P` Profiles, `G B` Batch, `G Y` History, `G S` Settings, `?` shortcut sheet, `Ctrl+K` command palette (navigate + jump to profile/job) — command palette is **Should**.
- Unsaved work guard: leaving the Editor with an unaccepted render asks "Discard this result?".

## 8. Forms

- Labels above fields, `--type-body-strong`; helper text below in secondary.
- Required fields marked with "Required" in helper text, not asterisks only.
- Validate on blur and on submit; token input validates live.
- Errors: field-level message + summary at top of form on submit if more than one error; focus moves to first invalid field.
- Submit button shows loading state; form disabled while submitting; never clear user input on server error.
- Destructive confirmation dialogs name the object and consequence: "Permanently delete profile *Receipt Token A*? 412 glyphs and 38 reference images will be deleted. This cannot be undone." Typing the name is required only for permanent profile deletion.
- Auth forms: 360 px wide card centred on surface-0, `--control-lg` inputs, password visibility toggle, caps-lock warning.

---

## 9. Loading, empty and error states

### 9.1 Patterns
| State | Pattern |
|-------|---------|
| Page loading (< 300 ms) | Nothing (avoid flash) |
| Page loading (≥ 300 ms) | Skeletons matching final layout |
| Background task | Tasks chip in top bar + inline progress where the result will appear |
| Long engine step | Step list with current step highlighted: `Removing old text → Placing glyphs → Matching light & grain → Checking quality` |
| Empty (first use) | Icon (32 px, secondary), one-line title, one-line explanation, one primary action |
| Empty (filtered) | "No results for these filters" + "Clear filters" ghost button |
| Recoverable error | Inline banner in the affected area with "Retry"; rest of the page stays usable |
| Field error | Inline field message |
| Fatal/server down | Full-width danger banner at top: "Traid engine is not responding." + Retry; content stays visible read-only |
| Session expired | Redirect to Sign in with toast "Session expired — sign in to continue"; return to previous URL |
| Forbidden / Not found | Centred message + "Go to Home" |

### 9.2 Copy rules
- Say what happened, why (if known), and what to do: "No glyphs for **Q**. Upload reference images that contain Q, or remove Q from the token."
- Error codes from the API are shown in small mono text under the message for support/debugging (`PROFILE_NOT_READY`).
- Never blame the user; never show stack traces.

---

## 10. Interactions and animation

| Token | Duration | Easing | Use |
|-------|----------|--------|-----|
| `--motion-fast` | 120 ms | ease-out | Hover, press, toggle |
| `--motion-base` | 180 ms | ease-out | Popovers, tabs indicator, panel collapse |
| `--motion-slow` | 240 ms | cubic-bezier(0.2, 0, 0, 1) | Dialog/drawer enter, result cross-fade |

Rules:
- Animate opacity and transform only. Never animate layout of the canvas.
- When a new render arrives, cross-fade the "After" image (240 ms) so the user perceives the change without jumping.
- Zoom and pan are immediate (no easing) except "Fit to screen" (180 ms).
- `prefers-reduced-motion: reduce` → all durations 0 ms except progress indicators; skeleton pulse off.
- No decorative motion, no looping animations except spinners/indeterminate progress.

### 10.1 Editor interactions
| Action | Mouse | Keyboard |
|--------|-------|----------|
| Pan | Space + drag, middle-drag | Arrow keys when canvas focused and no region selected |
| Zoom | Ctrl + wheel, pinch | `Ctrl+=` / `Ctrl+-`; `0` fit; `1` 100%; `2` 200%; `4` 400% |
| Toggle before/after | Click toggle | `\` |
| Split view | Drag slider | `S` |
| Mask overlay | Toggle | `M` |
| Glyph boxes overlay | Toggle | `G` |
| Select region | Click overlay or list row | `Tab` / `Shift+Tab` cycles regions |
| Move corner handle | Drag | Select handle `1–4`, arrows 1 px, Shift+arrows 10 px |
| Focus token input | — | `T` |
| Generate / re-generate | Primary button | `Ctrl+Enter` |
| Accept | Button | `Ctrl+Shift+A` |
| Reject | Button | `Ctrl+Shift+R` |
| Export | Button | `Ctrl+E` |
| Undo / redo adjustments | — | `Ctrl+Z` / `Ctrl+Shift+Z` |

### 10.2 Glyph review interactions
- Arrow keys move selection in grid; `Enter` confirm; `X` reject; type a character to relabel; `Shift+click` range select; `Ctrl+A` select all in group; `Space` large preview.

### 10.3 Drag and drop
- Whole Home and Editor canvas accept file drops. Profile References tab accepts multi-file drops. Invalid file type during drag shows "Not supported" in the drop zone before release.

---

## 11. Page-level layout guidance

### 11.1 Setup (first run) & Sign in
- Centred 360 px column on surface-0. Product wordmark "Traid" (Plex Sans 600, 24 px) with "by Xavier Sun" beneath in secondary.
- Setup is a 3-step vertical stepper: **Engine check** (list of models/device with status rows) → **Owner account** → **Acceptable use** (short text + required checkbox). Primary button "Finish setup".
- Footer of both screens: "Traid · Designed & developed by Xavier Sun".

### 11.2 Home
- Two-column (8/4).
- Left: large drop zone (min 280 px tall) "Drop a target image" + profile select (defaults to last used) + "Or browse files". Below: **Recent jobs** table (10 rows, thumbnail, old → new token, profile, status, time).
- Right: **Profiles** compact list with readiness badge and coverage %, "New profile" secondary button.
- Empty state (no profiles): drop zone replaced by guided card "1. Create a Style Profile · 2. Upload references · 3. Drop a target image".

### 11.3 Profiles list
- Table: name, status badge, glyphs (confirmed/total), coverage %, acceptance rate, last used, actions. Toggle "Show archived". Primary: "New profile" (dialog: name, surface type, description, charset preset, pattern). Surface type is a 4-option segmented control with a one-line hint each: *Print* (ink or toner on paper/labels) · *Paint* (painted or stencilled, e.g. walls) · *Laser mark* (colour-change marking on metal/plastic) · *Engraved* (cut or embossed, visible depth). The profiles table shows surface type as a neutral chip.

### 11.4 Profile detail
- Header: name, status badge, actions (Test in editor, Archive). Tabs below.
- **Overview**: metric rows (glyphs, coverage, acceptance rate, jobs), small line chart of acceptance rate over last 50 jobs (the only chart in the MVP), most-rejected glyphs strip, missing characters callout.
- **References**: drop zone strip at top; grid of thumbnails with status (processing, processed n glyphs, failed + reason); click opens drawer with image and detected characters overlaid; optional known-text field.
- **Glyphs**: left filter column (200 px: character list with counts, status filter, quality slider); main grid of glyph tiles grouped by character with sticky group headers; bulk action bar appears at bottom when selection > 0 (Confirm · Reject · Relabel…).
- **Coverage**: grid of coverage cells for the charset; legend; Ready rule text ("Needs ≥ 3 confirmed glyphs per character").
- **Settings**: form (surface type, charset, token pattern + strict toggle, alignment, spacing mode, ready threshold, use auto glyphs toggle).

### 11.5 Editor (full-bleed)
```
┌───────────┬──────────────────────────────────────────┬────────────────┐
│ Regions   │ Toolbar: zoom · fit · before/after ·      │ Inspector      │
│ 240 px    │ split · mask · glyph boxes · backdrop    │ 340 px         │
│           ├──────────────────────────────────────────┤                │
│ list of   │                                          │ Profile select │
│ detected  │              Canvas                      │ Old token      │
│ text with │        (image + overlays)                │ New token      │
│ conf. and │                                          │ [Generate]     │
│ "token"   │                                          │ Adjustments ▸  │
│ badge     │                                          │ Quality ▸      │
│           ├──────────────────────────────────────────┤ Accept/Reject  │
│           │ Status bar: zoom % · px coords · size    │ Export         │
└───────────┴──────────────────────────────────────────┴────────────────┘
```
- Inspector sections in order: **Token** (profile, detected old text read-only + "Not right? Edit", new token input, Generate primary) → **Adjustments** (collapsed until first render: position x/y, scale, spacing, weight, blur, ink tone, grain; "Reset all") → **Characters** (one chip per new character, click to see variants — Should) → **Quality** (metric rows with pass/warn) → **Decision** (Accept primary after render, Reject secondary, Export appears after accept).
- Primary button migrates: before render "Generate"; after render "Accept"; after accept "Export".
- Regions panel and inspector are collapsible (`[` and `]`).
- Status bar: zoom, cursor image coordinates, image size, engine device.

### 11.6 Batch
- Step layout across the top (Template → Values → Run → Review & export).
- **Values**: textarea (mono, one per line) + "Import CSV/TXT"; live validation list on the right with counts (valid / invalid / duplicates).
- **Run**: progress bar, count, ETA, Cancel.
- **Review**: results grid (thumbnail crops of the token area at 2× zoom, value, quality badge), sorted warnings first; click opens review drawer (before/after crop, quality, adjust, accept/reject). Bulk "Accept all passed". Primary: "Export accepted (n)".

### 11.7 History
- Filter bar (profile, status, date range, search token) above a table; rows open job detail page: large before/after viewer (read-only), parameters, quality report, audit entries, actions (Re-export, Open in editor, Delete).

### 11.8 Settings
- Left sub-navigation (200 px): Account · Engine · Export · Storage & backup · Audit log · About.
- **About** shows: product name and version, "Designed & developed by Xavier Sun", open-source model credits and licenses, Acceptable Use text.

---

## 12. Responsive behaviour

Traid is desktop-first. Image editing requires space and a precise pointer.

| Width | Behaviour |
|-------|-----------|
| ≥ 1440 px | Full layout; Editor shows both side panels. |
| 1280–1439 | Full layout; Editor regions panel collapses to 48 px icon strip by default. |
| 1024–1279 | Editor: regions panel hidden behind a toggle; inspector becomes an overlay drawer (340 px) toggled with `]`. List pages: 12-col grid collapses Home to single column. |
| 768–1023 | Read-mostly mode: Home, Profiles, History, Settings usable; Editor and Batch review show a notice "The editor needs a window at least 1024 px wide" with the job still viewable read-only. Nav rail stays. |
| < 768 | Not supported for editing; sign-in and read-only views stack vertically; nav rail becomes a top bar with menu. |

Rules: no horizontal page scroll at any supported width; tables scroll horizontally inside their container only; touch targets ≥ 32 px (≥ 40 px under 1024 px).

---

## 13. Accessibility requirements

- Conform to **WCAG 2.2 AA** for all non-canvas UI.
- Contrast: text ≥ 4.5:1, large text and UI component boundaries ≥ 3:1 (tokens in §3 meet this on surface-0/1/2).
- **Focus visible** on every interactive element: 2 px accent ring with 2 px offset; never removed.
- Full keyboard operation; logical tab order; skip link "Skip to content" on every page.
- Canvas content has an accessible equivalent: the Regions panel lists each detected region (text, confidence, selected state) as focusable items; the quality report and character chips are real DOM elements; canvas has `role="img"` with a live description ("Target image 4032 × 3024, token region selected: A7-204913").
- Live regions (`aria-live="polite"`) announce task progress milestones and render completion; errors use `assertive`.
- Status never conveyed by colour alone (icon + text + line style).
- All icons-only buttons have `aria-label` and tooltip.
- Dialogs trap focus, restore focus on close, close on `Esc`.
- Respect `prefers-reduced-motion`.
- Minimum target size 24 × 24 px (WCAG 2.5.8); default controls are 32 px.
- Form errors linked with `aria-describedby`; invalid fields `aria-invalid="true"`.
- Language attribute set; text resizable to 200% without loss of function on list pages.

---

## 14. Credits placement (owner requirement)

The credit "Xavier Sun" must appear in:
1. Nav rail bottom: "by Xavier Sun" (`--type-micro`, secondary).
2. Setup and Sign-in footers: "Traid · Designed & developed by Xavier Sun".
3. Settings → About: full credit block.
4. Browser tab title suffix: "— Traid".

Credits never appear inside exported images.
