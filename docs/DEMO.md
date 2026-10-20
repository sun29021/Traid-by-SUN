# Traid — showcase demo script

About 10 minutes. Covers PRD journeys J2 (train a profile) → J3 (edit) → J4 (batch) → learning.
Prepare beforehand: Traid running (`scripts\start.ps1`), a profile already trained on your
real reference photos, 3–4 target photos, and a fresh profile name for the live training part.

## 0. Opening (30 s)

- Home screen. "Traid replaces short text in a photo — a serial number, a label, painted
  lettering, a laser mark — using real characters it learned from your own photos.
  It never draws with a font."
- Point at the credit: "Designed & developed by Xavier Sun" (nav rail, Settings → About).

## 1. Teach a style (J2, 2 min)

1. Profiles → **New profile**, choose the surface type (print / paint / laser mark /
   engraved) and the character set.
2. References → drop 3–5 photos of the same kind of text. Extraction runs in the
   background (progress in the top bar).
3. Glyphs → select all (Ctrl+A), confirm (Enter); show relabelling by typing a character
   and rejecting a bad crop with Delete.
4. Coverage → every character green → profile **Ready**.

Talking point: every glyph is a real crop with measured blur, noise, ink colour and
lighting; the engine picks the best-matching ones per photo.

## 2. Edit one photo (J3, 3 min — 5 interactions)

1. Home → drop a target photo (profile is remembered). The token is found and
   preselected; the old text is read by OCR.
2. Type the new token → **Ctrl+Enter**.
3. Show: before/after (`\`), split view (`S`), mask overlay (`M`), 100 % zoom on the
   characters. Characters panel: which ones were kept, which came from this photo,
   which from the bank. Quality report: OCR read-back, seam, noise, sharpness, colour,
   "outside unchanged".
4. Nudge one adjustment (e.g. ink tone) → it re-renders in well under a second; Ctrl+Z.
5. **Accept** → **Export**: same format, size, DPI and colour profile; the file carries
   an "edited with Traid" marker.

Talking point: equal-length edits replace only the changed characters; everything else is
the camera's own pixels, bit-identical outside the edited area.

## 3. Batch (J4, 2 min)

1. In the editor: **Use as batch template** (or Batch → choose the accepted edit).
2. Paste 10–20 values; invalid ones are listed with the reason before starting.
3. Run → progress with ETA → review grid (warnings first) → **Accept all passed** →
   **Export accepted** → ZIP with predictable names.

## 4. Learning (1 min)

- Profile → Overview → **Learning**: acceptance rate, the 14-day chart, and the
  adjustments new edits now start from.
- History → open an edit → its activity trail (accepted, exported).

## 5. Evidence (1 min)

- `backend\tests\eval\showcase_report.py --data-dir ..\data` → PRD §18 table
  (read-back rate, acceptance without fine-tuning, time per token, learning effect,
  stability).
- Blind test: `blind_kit.py make` before the showcase, viewers fill `sheet.csv`,
  `blind_kit.py score` afterwards (target: viewers spot the edit in ≤ 60 % of pairs).

## Responsible use (say it)

Traid is for images you own or are authorised to change — product shots, mock-ups,
labels, your own archives. It refuses nothing technically, so the Welcome screen asks for
that commitment, exports are marked as edited by default, and every decision is in the
audit log.
