import { describe, expect, it } from 'vitest';

import { changedCount, DEFAULT_PARAMS, editorReducer, initialEditorState } from './editorStore';

describe('editorReducer', () => {
  it('clamps adjustments to their API ranges', () => {
    let state = initialEditorState();
    state = editorReducer(state, { type: 'set', key: 'scale', value: 5 });
    state = editorReducer(state, { type: 'set', key: 'dx', value: -80 });

    expect(state.params.scale).toBe(1.2);
    expect(state.params.dx).toBe(-50);
  });

  it('undoes and redoes adjustment changes', () => {
    let state = initialEditorState();
    state = editorReducer(state, { type: 'set', key: 'weight', value: 0.5 });
    state = editorReducer(state, { type: 'set', key: 'blur', value: 1 });

    state = editorReducer(state, { type: 'undo' });
    expect(state.params).toMatchObject({ weight: 0.5, blur: 0 });
    state = editorReducer(state, { type: 'undo' });
    expect(state.params).toEqual(DEFAULT_PARAMS);
    expect(editorReducer(state, { type: 'undo' })).toBe(state); // nothing left

    state = editorReducer(state, { type: 'redo' });
    expect(state.params.weight).toBe(0.5);
  });

  it('a new change clears the redo history; no-op changes are not recorded', () => {
    let state = initialEditorState();
    state = editorReducer(state, { type: 'set', key: 'grain', value: 2 });
    state = editorReducer(state, { type: 'undo' });
    state = editorReducer(state, { type: 'set', key: 'grain', value: 1 }); // same as current

    expect(state.future).toHaveLength(1);
    state = editorReducer(state, { type: 'set', key: 'ink_tone', value: 0.3 });
    expect(state.future).toHaveLength(0);
  });

  it('sets and clears glyph overrides, counted as changes', () => {
    let state = initialEditorState();
    state = editorReducer(state, { type: 'override', position: 2, glyphId: 'g1' });
    expect(state.params.glyph_overrides).toEqual({ '2': 'g1' });
    expect(changedCount(state.params)).toBe(1);

    state = editorReducer(state, { type: 'override', position: 2, glyphId: null });
    expect(state.params.glyph_overrides).toEqual({});
  });

  it('reset all returns to defaults as one undoable step', () => {
    let state = initialEditorState();
    state = editorReducer(state, { type: 'set', key: 'dx', value: 3 });
    state = editorReducer(state, { type: 'set', key: 'dy', value: -2 });
    state = editorReducer(state, { type: 'reset' });

    expect(changedCount(state.params)).toBe(0);
    state = editorReducer(state, { type: 'undo' });
    expect(state.params).toMatchObject({ dx: 3, dy: -2 });
  });

  it('toggles views and keeps the split inside the image', () => {
    let state = initialEditorState();
    state = editorReducer(state, { type: 'toggleView' });
    expect(state.view).toBe('before');
    state = editorReducer(state, { type: 'toggleSplit' });
    expect(state.view).toBe('split');
    state = editorReducer(state, { type: 'split', value: 1.7 });
    expect(state.split).toBe(1);
  });
});
