import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, noActiveTasks, okHealth, welcomeRoute } from '@/test/mockApi';
import { renderApp } from '@/test/renderApp';

const base = [okHealth, welcomeRoute(true), noActiveTasks];

const FILE = {
  id: 'f1',
  url: '/api/v1/files/f1',
  thumb_url: '/api/v1/files/f1/thumb',
  mime_type: 'image/png',
  width: 960,
  height: 640,
  byte_size: 1000,
  original_name: 'receipt.png',
};

const JOB = {
  id: 'j1',
  profile_id: 'p1',
  batch_id: null,
  status: 'accepted',
  input: FILE,
  result: { ...FILE, id: 'f2', url: '/api/v1/files/f2', thumb_url: '/api/v1/files/f2/thumb' },
  mask: null,
  regions: [],
  selected_region_id: null,
  selected_quad: null,
  original_text: 'A7-204913',
  new_text: 'A7-204914',
  params: {
    dx: 0,
    dy: 0,
    scale: 1,
    spacing: 0,
    weight: 0,
    blur: 0,
    ink_tone: 0,
    grain: 1,
    glyph_overrides: {},
  },
  glyphs_used: [],
  quality: {
    overall: 'pass',
    checks: [{ id: 'ocr_readback', status: 'pass', value: 'A7-204914' }],
  },
  layout_mode: 'slots',
  warnings: [],
  engine_version: 'glyph_transplant@1.0.0',
  seed: 4,
  reject_reason: null,
  error_code: null,
  accepted_at: '2026-10-20T10:00:00.000Z',
  exported_at: null,
  created_at: '2026-10-20T10:00:00.000Z',
  updated_at: '2026-10-20T10:00:00.000Z',
};

const PROFILES = { path: '/profiles', body: { data: [{ id: 'p1', name: 'Receipt token A' }] } };

describe('History', () => {
  it('lists jobs and keeps filters in the URL', async () => {
    const fetchMock = mockApi([
      ...base,
      PROFILES,
      { path: '/jobs', body: { data: [JOB], meta: { next_cursor: null, count: 1 } } },
    ]);
    const router = renderApp('/history?status=accepted');

    const row = await screen.findByRole('row', { name: /A7-204913 → A7-204914/ });
    expect(row).toHaveTextContent('Accepted');
    expect(row).toHaveTextContent('Pass');
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/jobs?status=accepted')),
    ).toBe(true);

    fireEvent.change(screen.getByLabelText('Token starts with'), { target: { value: 'A7-2049' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(router.state.location.search).toContain('q=A7-2049'));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('q=A7-2049'))).toBe(true),
    );
  });

  it('shows a job with its quality, adjustments and activity', async () => {
    mockApi([
      ...base,
      { path: '/jobs/j1', body: { data: JOB } },
      {
        path: '/audit',
        body: {
          data: [
            {
              id: 'a1',
              user_id: 'u1',
              action: 'job.accepted',
              subject_type: 'edit_job',
              subject_id: 'j1',
              details: {},
              created_at: '2026-10-20T10:00:00.000Z',
            },
          ],
          meta: { next_cursor: null, count: 1 },
        },
      },
    ]);
    renderApp('/history/j1');

    expect(await screen.findByRole('button', { name: 'Export again' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Quality' })).toHaveTextContent('A7-204914');
    expect(screen.getByRole('region', { name: 'Adjustments' })).toHaveTextContent(
      'glyph_transplant@1.0.0',
    );
    expect(await screen.findByText('Edit accepted')).toBeInTheDocument();
  });
});
