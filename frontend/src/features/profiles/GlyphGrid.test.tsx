import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { Glyph } from '@/lib/api/types';

import { GlyphGrid } from './GlyphGrid';

function glyph(id: string, char: string, status: Glyph['status'] = 'auto'): Glyph {
  return {
    id,
    profile_id: 'p',
    char,
    status,
    crop_url: `/api/v1/files/${id}`,
    source: { type: 'reference', id: 'r' },
    metrics: {
      cap_height_px: 40,
      stroke_width_px: 6,
      blur_sigma: 1,
      noise_sigma: 1,
      ink_color: '#202020',
      bg_luma: 0.9,
      contrast: 0.6,
      angle_deg: 0,
      light_dir_deg: null,
    },
    ocr_confidence: 0.98,
    quality_score: 0.9,
    use_count: 0,
    accept_count: 0,
    reject_count: 0,
    created_at: '2026-10-20T10:00:00.000Z',
  };
}

const GLYPHS = [glyph('a1', 'A'), glyph('a2', 'A'), glyph('b1', 'B', 'confirmed')];

function Harness(props: {
  onConfirm?: (ids: string[]) => void;
  onReject?: (ids: string[]) => void;
  onRelabel?: (ids: string[], char: string) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [focused, setFocused] = useState<string | null>(null);
  return (
    <GlyphGrid
      glyphs={GLYPHS}
      selected={selected}
      focusedId={focused}
      onFocus={setFocused}
      onSelectionChange={setSelected}
      onConfirm={props.onConfirm ?? vi.fn()}
      onReject={props.onReject ?? vi.fn()}
      onRelabel={props.onRelabel ?? vi.fn()}
    />
  );
}

describe('GlyphGrid', () => {
  it('groups glyphs by character as a multi-select listbox', () => {
    render(<Harness />);

    expect(screen.getByRole('listbox', { name: 'Glyphs' })).toHaveAttribute(
      'aria-multiselectable',
      'true',
    );
    expect(screen.getByRole('group', { name: 'Character A' })).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(screen.getAllByRole('option')[2]).toHaveAccessibleName(/B, Confirmed, quality 90%/);
  });

  it('keeps only one tile in the tab order and moves with the arrow keys', () => {
    render(<Harness />);
    const [first, second] = screen.getAllByRole('option');

    expect(first).toHaveAttribute('tabindex', '0');
    expect(second).toHaveAttribute('tabindex', '-1');
    first?.focus();
    fireEvent.keyDown(first as HTMLElement, { key: 'ArrowRight' });
    expect(second).toHaveFocus();
  });

  it('acts on the focused glyph when nothing is selected', () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();
    render(<Harness onConfirm={onConfirm} onReject={onReject} />);
    const first = screen.getAllByRole('option')[0] as HTMLElement;
    first.focus();

    fireEvent.keyDown(first, { key: 'Enter' });
    fireEvent.keyDown(first, { key: 'Delete' });

    expect(onConfirm).toHaveBeenCalledWith(['a1']);
    expect(onReject).toHaveBeenCalledWith(['a1']);
  });

  it('selects with Space, Ctrl+A and shift-click, and relabels by typing', () => {
    const onRelabel = vi.fn();
    render(<Harness onRelabel={onRelabel} />);
    const [first, second, third] = screen.getAllByRole('option') as HTMLElement[];

    first?.focus();
    fireEvent.keyDown(first as HTMLElement, { key: ' ' });
    expect(first).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(third as HTMLElement, { shiftKey: true });
    expect(second).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(first as HTMLElement, { key: '4' });
    expect(onRelabel).toHaveBeenCalledWith(['a1', 'a2', 'b1'], '4');

    fireEvent.keyDown(first as HTMLElement, { key: 'Escape' });
    expect(screen.queryAllByRole('option', { selected: true })).toHaveLength(0);

    fireEvent.keyDown(first as HTMLElement, { key: 'a', ctrlKey: true });
    expect(screen.getAllByRole('option', { selected: true })).toHaveLength(3);
  });

  it('stops handled keys from reaching global shortcuts', () => {
    const onWindowKey = vi.fn();
    window.addEventListener('keydown', onWindowKey);
    render(<Harness />);
    const first = screen.getAllByRole('option')[0] as HTMLElement;

    fireEvent.keyDown(first, { key: 'g' });

    expect(onWindowKey).not.toHaveBeenCalled();
    window.removeEventListener('keydown', onWindowKey);
  });
});
