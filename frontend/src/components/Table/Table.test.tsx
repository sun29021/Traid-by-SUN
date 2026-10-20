import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { type Column, Table } from './Table';

interface Job {
  id: string;
  token: string;
  score: number;
}

const ROWS: Job[] = [
  { id: 'a', token: 'A7-1', score: 0.9 },
  { id: 'b', token: 'A7-2', score: 0.4 },
];
const COLUMNS: Column<Job>[] = [
  { key: 'token', header: 'Token', cell: (row) => row.token, sortable: true },
  { key: 'score', header: 'Score', cell: (row) => row.score, align: 'end' },
];

describe('Table', () => {
  it('reports sort changes and exposes aria-sort', () => {
    const onSortChange = vi.fn();
    render(
      <Table
        caption="Jobs"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(row) => row.id}
        sort={{ key: 'token', direction: 'asc' }}
        onSortChange={onSortChange}
      />,
    );

    expect(screen.getByRole('columnheader', { name: 'Token' })).toHaveAttribute(
      'aria-sort',
      'ascending',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Token' }));
    expect(onSortChange).toHaveBeenCalledWith({ key: 'token', direction: 'desc' });
  });

  it('opens rows by click or keyboard and marks the selected row', () => {
    const onRowClick = vi.fn();
    render(
      <Table
        caption="Jobs"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(row) => row.id}
        onRowClick={onRowClick}
        selectedKey="b"
      />,
    );
    const rows = screen.getAllByRole('row').slice(1);

    fireEvent.click(rows[0] as HTMLElement);
    fireEvent.keyDown(rows[1] as HTMLElement, { key: 'Enter' });

    expect(onRowClick.mock.calls.map(([row]) => (row as Job).id)).toEqual(['a', 'b']);
    expect(rows[1]).toHaveAttribute('aria-selected', 'true');
  });
});
