import { ArrowDown, ArrowUp } from 'lucide-react';
import type { KeyboardEvent, ReactNode } from 'react';

import styles from './Table.module.css';

export interface Column<Row> {
  key: string;
  header: string;
  cell: (row: Row) => ReactNode;
  sortable?: boolean;
  align?: 'start' | 'end';
}

export interface SortState {
  key: string;
  direction: 'asc' | 'desc';
}

export interface TableProps<Row> {
  caption: string;
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => string;
  onRowClick?: (row: Row) => void;
  selectedKey?: string | null;
  sort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
}

/**
 * Dense data table (DESIGN.md §6.3): sticky header, sortable headers, clickable rows.
 * Sorting is controlled by the parent (usually stored in the URL). Empty and loading
 * states are rendered by the page, not here.
 */
export function Table<Row>({
  caption,
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
  sort,
  onSortChange,
}: TableProps<Row>) {
  const toggleSort = (key: string) => {
    const direction = sort?.key === key && sort.direction === 'asc' ? 'desc' : 'asc';
    onSortChange?.({ key, direction });
  };

  const onRowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: Row) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onRowClick?.(row);
    }
  };

  return (
    // Focusable so keyboard users can scroll a wide table (WCAG 2.1.1, axe scrollable-region).
    <div className={styles.scroller} role="region" aria-label={caption} tabIndex={0}>
      <table className={styles.table}>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => {
              const active = sort?.key === column.key;
              const ariaSort = active
                ? sort.direction === 'asc'
                  ? 'ascending'
                  : 'descending'
                : undefined;
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={ariaSort}
                  className={column.align === 'end' ? styles.end : undefined}
                >
                  {column.sortable && onSortChange ? (
                    <button
                      type="button"
                      className={styles.sortButton}
                      onClick={() => toggleSort(column.key)}
                    >
                      {column.header}
                      {active && sort.direction === 'asc' ? <ArrowUp aria-hidden /> : null}
                      {active && sort.direction === 'desc' ? <ArrowDown aria-hidden /> : null}
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            const selected = key === selectedKey;
            return (
              <tr
                key={key}
                className={[onRowClick ? styles.clickable : '', selected ? styles.selected : '']
                  .filter(Boolean)
                  .join(' ')}
                aria-selected={onRowClick ? selected : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={onRowClick ? (event) => onRowKeyDown(event, row) : undefined}
              >
                {columns.map((column) => (
                  <td key={column.key} className={column.align === 'end' ? styles.end : undefined}>
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
