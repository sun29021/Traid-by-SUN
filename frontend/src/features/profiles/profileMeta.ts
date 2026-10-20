import type { Tone } from '@/components';
import type { GlyphStatus, ProfileStatus, ReferenceStatus, SurfaceType } from '@/lib/api/types';

export const SURFACE_TYPES: readonly { value: SurfaceType; label: string; hint: string }[] = [
  { value: 'print', label: 'Print', hint: 'Ink or toner on paper and labels' },
  { value: 'paint', label: 'Paint', hint: 'Painted or stencilled, e.g. on walls' },
  { value: 'laser_mark', label: 'Laser mark', hint: 'Colour-change marking on metal or plastic' },
  { value: 'engraved', label: 'Engraved', hint: 'Cut or embossed, with visible depth' },
];

export function surfaceLabel(value: SurfaceType): string {
  return SURFACE_TYPES.find((s) => s.value === value)?.label ?? value;
}

const DIGITS = '0123456789';
const UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const LOWER = 'abcdefghijklmnopqrstuvwxyz';

/** Character set presets (PRD D-07). They only fill the charset field. */
export const CHARSET_PRESETS = [
  {
    id: 'upper_digits',
    label: 'Uppercase + digits + - / # space',
    charset: `${DIGITS}${UPPER}-/# `,
  },
  { id: 'digits', label: 'Digits only', charset: DIGITS },
  {
    id: 'full_latin',
    label: 'Full Latin (A–Z, a–z, 0–9, punctuation)',
    charset: `${DIGITS}${UPPER}${LOWER} -/#.,:;()&+'"!?@%*_=`,
  },
  { id: 'custom', label: 'Custom…', charset: '' },
] as const;

export type CharsetPresetId = (typeof CHARSET_PRESETS)[number]['id'];

export function presetFor(charset: string): CharsetPresetId {
  return CHARSET_PRESETS.find((p) => p.id !== 'custom' && p.charset === charset)?.id ?? 'custom';
}

export const PROFILE_STATUS: Record<ProfileStatus, { tone: Tone; label: string }> = {
  draft: { tone: 'neutral', label: 'Not ready' },
  training: { tone: 'info', label: 'Training' },
  needs_review: { tone: 'warning', label: 'Needs review' },
  ready: { tone: 'success', label: 'Ready' },
};

export const REFERENCE_STATUS: Record<ReferenceStatus, { tone: Tone; label: string }> = {
  pending: { tone: 'neutral', label: 'Waiting' },
  processing: { tone: 'info', label: 'Extracting' },
  processed: { tone: 'success', label: 'Processed' },
  failed: { tone: 'danger', label: 'Failed' },
};

export const GLYPH_STATUS: Record<GlyphStatus, { tone: Tone; label: string }> = {
  auto: { tone: 'warning', label: 'To review' },
  confirmed: { tone: 'success', label: 'Confirmed' },
  rejected: { tone: 'danger', label: 'Rejected' },
};

/** Plain-language reasons for reference failures (DESIGN.md §9.2). */
export const REFERENCE_ERRORS: Record<string, string> = {
  NO_TEXT_FOUND: 'No text from this profile was found in the image.',
  SEGMENTATION_FAILED: 'Text was found but individual characters could not be separated.',
  MODEL_UNAVAILABLE: 'The AI models are not installed. Run scripts\\fetch_models.py.',
  STORAGE_ERROR: 'The stored image could not be read.',
  INTERNAL_ERROR: 'Something went wrong while processing this image.',
  TASK_INTERRUPTED: 'Traid was closed while this image was processed.',
};

export function displayChar(char: string): string {
  return char === ' ' ? '␣' : char;
}
