import type { RenderParams } from '@/lib/api/types';

/** Adjustment fields shown in the panel, with API.md §3.6 ranges. */
export const ADJUSTMENTS = [
  { key: 'dx', label: 'Position x', min: -50, max: 50, step: 0.5, unit: 'px' },
  { key: 'dy', label: 'Position y', min: -50, max: 50, step: 0.5, unit: 'px' },
  { key: 'scale', label: 'Scale', min: 0.8, max: 1.2, step: 0.01, unit: '×' },
  { key: 'spacing', label: 'Spacing', min: -10, max: 10, step: 0.5, unit: 'px' },
  { key: 'weight', label: 'Weight', min: -1, max: 1, step: 0.05, unit: '' },
  { key: 'blur', label: 'Blur', min: -2, max: 2, step: 0.05, unit: 'σ' },
  { key: 'ink_tone', label: 'Ink tone', min: -1, max: 1, step: 0.05, unit: '' },
  { key: 'grain', label: 'Grain', min: 0, max: 3, step: 0.05, unit: '×' },
] as const;

export type AdjustmentKey = (typeof ADJUSTMENTS)[number]['key'];

export const DEFAULT_PARAMS: RenderParams = {
  dx: 0,
  dy: 0,
  scale: 1,
  spacing: 0,
  weight: 0,
  blur: 0,
  ink_tone: 0,
  grain: 1,
  glyph_overrides: {},
};

const HISTORY_LIMIT = 50;

export type ViewMode = 'after' | 'before' | 'split';

export interface EditorState {
  params: RenderParams;
  past: RenderParams[];
  future: RenderParams[];
  view: ViewMode;
  split: number; // 0..1, position of the split line
  showMask: boolean;
  showRegions: boolean;
}

export type EditorAction =
  | { type: 'load'; params: RenderParams }
  | { type: 'set'; key: AdjustmentKey; value: number }
  | { type: 'override'; position: number; glyphId: string | null }
  | { type: 'reset' }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'view'; view: ViewMode }
  | { type: 'toggleView' }
  | { type: 'toggleSplit' }
  | { type: 'split'; value: number }
  | { type: 'toggleMask' }
  | { type: 'toggleRegions' };

export function initialEditorState(params: RenderParams = DEFAULT_PARAMS): EditorState {
  return {
    params,
    past: [],
    future: [],
    view: 'after',
    split: 0.5,
    showMask: false,
    showRegions: true,
  };
}

function clamp(key: AdjustmentKey, value: number): number {
  const field = ADJUSTMENTS.find((a) => a.key === key);
  if (!field || Number.isNaN(value)) return DEFAULT_PARAMS[key];
  return Math.min(field.max, Math.max(field.min, value));
}

function sameParams(a: RenderParams, b: RenderParams): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function commit(state: EditorState, params: RenderParams): EditorState {
  if (sameParams(params, state.params)) return state;
  return {
    ...state,
    params,
    past: [...state.past, state.params].slice(-HISTORY_LIMIT),
    future: [],
  };
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case 'load':
      return { ...state, params: action.params, past: [], future: [] };
    case 'set':
      return commit(state, { ...state.params, [action.key]: clamp(action.key, action.value) });
    case 'override': {
      const key = String(action.position);
      const others = Object.entries(state.params.glyph_overrides ?? {}).filter(([k]) => k !== key);
      const overrides = Object.fromEntries(
        action.glyphId ? [...others, [key, action.glyphId]] : others,
      ) as Record<string, string>;
      return commit(state, { ...state.params, glyph_overrides: overrides });
    }
    case 'reset':
      return commit(state, { ...DEFAULT_PARAMS, glyph_overrides: {} });
    case 'undo': {
      const previous = state.past.at(-1);
      if (!previous) return state;
      return {
        ...state,
        params: previous,
        past: state.past.slice(0, -1),
        future: [state.params, ...state.future],
      };
    }
    case 'redo': {
      const [next, ...rest] = state.future;
      if (!next) return state;
      return { ...state, params: next, past: [...state.past, state.params], future: rest };
    }
    case 'view':
      return { ...state, view: action.view };
    case 'toggleView':
      return { ...state, view: state.view === 'before' ? 'after' : 'before' };
    case 'toggleSplit':
      return { ...state, view: state.view === 'split' ? 'after' : 'split' };
    case 'split':
      return { ...state, split: Math.min(1, Math.max(0, action.value)) };
    case 'toggleMask':
      return { ...state, showMask: !state.showMask };
    case 'toggleRegions':
      return { ...state, showRegions: !state.showRegions };
  }
}

/** Number of adjustments that differ from the defaults (shown on "Reset all"). */
export function changedCount(params: RenderParams): number {
  return (
    ADJUSTMENTS.filter((a) => (params[a.key] ?? DEFAULT_PARAMS[a.key]) !== DEFAULT_PARAMS[a.key])
      .length + Object.keys(params.glyph_overrides ?? {}).length
  );
}
