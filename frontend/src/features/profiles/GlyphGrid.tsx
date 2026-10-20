import { type KeyboardEvent, type MouseEvent, useMemo, useRef } from 'react';

import type { Glyph } from '@/lib/api/types';

import styles from './Glyphs.module.css';
import { displayChar, GLYPH_STATUS } from './profileMeta';

export interface GlyphGridProps {
  glyphs: readonly Glyph[];
  selected: ReadonlySet<string>;
  focusedId: string | null;
  onFocus: (id: string) => void;
  onSelectionChange: (ids: Set<string>) => void;
  /** Keyboard review on the selection (or the focused glyph when nothing is selected). */
  onConfirm: (ids: string[]) => void;
  onReject: (ids: string[]) => void;
  onRelabel: (ids: string[], char: string) => void;
}

interface Group {
  char: string;
  glyphs: Glyph[];
}

function groupByChar(glyphs: readonly Glyph[]): Group[] {
  const groups: Group[] = [];
  for (const glyph of glyphs) {
    const last = groups.at(-1);
    if (last && last.char === glyph.char) last.glyphs.push(glyph);
    else groups.push({ char: glyph.char, glyphs: [glyph] });
  }
  return groups;
}

/**
 * Glyph review grid (DESIGN.md §6.3, §10.2). A listbox of tiles grouped by character;
 * only the focused tile is in the tab order (roving tabindex).
 */
export function GlyphGrid({
  glyphs,
  selected,
  focusedId,
  onFocus,
  onSelectionChange,
  onConfirm,
  onReject,
  onRelabel,
}: GlyphGridProps) {
  const groups = useMemo(() => groupByChar(glyphs), [glyphs]);
  const order = useMemo(() => glyphs.map((g) => g.id), [glyphs]);
  const tiles = useRef(new Map<string, HTMLButtonElement>());
  const anchor = useRef<string | null>(null);
  const current = focusedId && order.includes(focusedId) ? focusedId : (order[0] ?? null);

  const focusTile = (id: string | undefined) => {
    if (!id) return;
    onFocus(id);
    tiles.current.get(id)?.focus();
  };

  /** The nearest tile in the row above/below (rows wrap, groups break rows). */
  const vertical = (id: string, direction: 1 | -1): string | undefined => {
    const origin = tiles.current.get(id)?.getBoundingClientRect();
    if (!origin) return undefined;
    let best: { id: string; score: number } | undefined;
    for (const other of order) {
      const rect = tiles.current.get(other)?.getBoundingClientRect();
      if (!rect || other === id) continue;
      const dy = (rect.top - origin.top) * direction;
      if (dy <= origin.height / 2) continue;
      const score = dy * 4 + Math.abs(rect.left - origin.left);
      if (!best || score < best.score) best = { id: other, score };
    }
    return best?.id;
  };

  const targets = (): string[] => (selected.size ? [...selected] : current ? [current] : []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!current) return;
    const index = order.indexOf(current);
    let handled = true;
    if (event.key === 'ArrowRight') focusTile(order[Math.min(index + 1, order.length - 1)]);
    else if (event.key === 'ArrowLeft') focusTile(order[Math.max(index - 1, 0)]);
    else if (event.key === 'ArrowDown') focusTile(vertical(current, 1));
    else if (event.key === 'ArrowUp') focusTile(vertical(current, -1));
    else if (event.key === 'Home') focusTile(order[0]);
    else if (event.key === 'End') focusTile(order.at(-1));
    else if (event.key === ' ') {
      const next = new Set(selected);
      if (next.has(current)) next.delete(current);
      else next.add(current);
      anchor.current = current;
      onSelectionChange(next);
    } else if (event.key === 'Enter') onConfirm(targets());
    else if (event.key === 'Delete' || event.key === 'Backspace') onReject(targets());
    else if (event.key === 'Escape') onSelectionChange(new Set());
    else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
      onSelectionChange(new Set(order));
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      onRelabel(targets(), event.key);
    } else handled = false;
    if (handled) {
      event.preventDefault();
      event.stopPropagation(); // keep global G-shortcuts from also firing
    }
  };

  const onClick = (event: MouseEvent, id: string) => {
    onFocus(id);
    if (event.shiftKey && anchor.current) {
      const from = order.indexOf(anchor.current);
      const to = order.indexOf(id);
      const range = order.slice(Math.min(from, to), Math.max(from, to) + 1);
      onSelectionChange(new Set([...selected, ...range]));
      return;
    }
    anchor.current = id;
    const next = new Set(event.ctrlKey || event.metaKey ? selected : []);
    if (selected.has(id) && (event.ctrlKey || event.metaKey)) next.delete(id);
    else next.add(id);
    onSelectionChange(next);
  };

  return (
    <div
      role="listbox"
      aria-label="Glyphs"
      aria-multiselectable="true"
      className={styles.grid}
      onKeyDown={onKeyDown}
    >
      {groups.map((group) => (
        <div
          key={group.char}
          role="group"
          className={styles.group}
          aria-label={`Character ${group.char}`}
        >
          {/* Visual heading; the group label carries the same text for screen readers. */}
          <h4 className={styles.groupHeader} aria-hidden>
            <span className={styles.groupChar}>{displayChar(group.char)}</span>
            <span>
              {group.glyphs.length} glyph{group.glyphs.length === 1 ? '' : 's'}
            </span>
          </h4>
          <div className={styles.tiles}>
            {group.glyphs.map((glyph) => (
              <button
                key={glyph.id}
                ref={(element) => {
                  if (element) tiles.current.set(glyph.id, element);
                  else tiles.current.delete(glyph.id);
                }}
                type="button"
                role="option"
                aria-selected={selected.has(glyph.id)}
                aria-label={`${displayChar(glyph.char)}, ${GLYPH_STATUS[glyph.status].label}, quality ${Math.round(glyph.quality_score * 100)}%`}
                tabIndex={glyph.id === current ? 0 : -1}
                data-status={glyph.status}
                data-backdrop={glyph.metrics.bg_luma >= 0.5 ? 'light' : 'dark'}
                className={styles.tile}
                onClick={(event) => onClick(event, glyph.id)}
                onFocus={() => onFocus(glyph.id)}
              >
                <span className={styles.tileChar} aria-hidden>
                  {displayChar(glyph.char)}
                </span>
                <img src={glyph.crop_url} alt="" className={styles.crop} loading="lazy" />
                <span className={styles.quality} aria-hidden>
                  <span
                    className={styles.qualityFill}
                    style={{ width: `${Math.round(glyph.quality_score * 100)}%` }}
                  />
                </span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
