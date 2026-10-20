import { type KeyboardEvent, type ReactNode, useRef } from 'react';

import styles from './Tabs.module.css';

export interface TabItem {
  id: string;
  label: string;
}

export interface TabsProps {
  /** Accessible name of the tab list. */
  label: string;
  /** Prefix for tab/panel ids; use the same value on the matching TabPanel. */
  idPrefix: string;
  items: readonly TabItem[];
  value: string;
  onChange: (id: string) => void;
}

/** WAI-ARIA tabs with arrow/Home/End keys (DESIGN.md §7). State usually lives in the URL. */
export function Tabs({ label, idPrefix, items, value, onChange }: TabsProps) {
  const refs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const focusAt = (index: number) => {
    const item = items[(index + items.length) % items.length];
    if (!item) return;
    onChange(item.id);
    refs.current.get(item.id)?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const moves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: items.length - 1,
    };
    const target = moves[event.key];
    if (target !== undefined) {
      event.preventDefault();
      focusAt(target);
    }
  };

  return (
    <div role="tablist" aria-label={label} className={styles.list}>
      {items.map((item, index) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            ref={(element) => {
              if (element) refs.current.set(item.id, element);
              else refs.current.delete(item.id);
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${item.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${item.id}`}
            tabIndex={selected ? 0 : -1}
            className={styles.tab}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  idPrefix,
  id,
  children,
}: {
  idPrefix: string;
  id: string;
  children: ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-tab-${id}`}
      tabIndex={0}
      className={styles.panel}
    >
      {children}
    </div>
  );
}
