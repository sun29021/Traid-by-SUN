import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, noActiveTasks, okHealth, welcomeRoute } from '@/test/mockApi';
import { renderApp } from '@/test/renderApp';

const base = [okHealth, welcomeRoute(true), noActiveTasks];

const PROFILE = {
  id: 'p1',
  name: 'Receipt token A',
  description: null,
  surface_type: 'print',
  charset: 'A7-204913',
  token_pattern: null,
  pattern_strict: false,
  alignment: 'auto',
  spacing_mode: 'auto',
  ready_threshold: 2,
  use_auto_glyphs: false,
  engine: 'glyph_transplant',
  status: 'ready',
  coverage: { ready_chars: 9, total_chars: 9, missing: [] },
  stats: {
    glyphs_confirmed: 18,
    glyphs_auto: 0,
    references: 2,
    jobs_accepted: 0,
    acceptance_rate: null,
  },
  learned_params: {},
  archived_at: null,
  created_at: '2026-10-20T10:00:00.000Z',
  updated_at: '2026-10-20T10:00:00.000Z',
};

const FILE = {
  id: 'f1',
  url: '/api/v1/files/f1',
  thumb_url: '/api/v1/files/f1/thumb',
  mime_type: 'image/jpeg',
  width: 960,
  height: 640,
  byte_size: 1000,
  original_name: 'receipt.jpg',
};

const QUAD = [
  [300, 280],
  [660, 280],
  [660, 340],
  [300, 340],
];

const JOB = {
  id: 'j1',
  profile_id: 'p1',
  batch_id: null,
  status: 'detected',
  input: FILE,
  result: null,
  mask: null,
  regions: [{ id: 'r1', quad: QUAD, text: 'A7-204913', confidence: 0.98, score: 0.9, reasons: [] }],
  selected_region_id: 'r1',
  selected_quad: QUAD,
  original_text: 'A7-204913',
  new_text: null,
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
  quality: null,
  layout_mode: null,
  warnings: [],
  engine_version: null,
  seed: 1,
  reject_reason: null,
  error_code: null,
  accepted_at: null,
  exported_at: null,
  created_at: '2026-10-20T10:00:00.000Z',
  updated_at: '2026-10-20T10:00:00.000Z',
};

const RENDERED = {
  ...JOB,
  status: 'rendered',
  new_text: 'A7-204914',
  result: { ...FILE, id: 'f2', url: '/api/v1/files/f2' },
  mask: { ...FILE, id: 'f3', url: '/api/v1/files/f3' },
  layout_mode: 'slots',
  glyphs_used: [{ position: 8, char: '4', source: 'same_image', glyph_id: null, score: 0.9 }],
  quality: {
    overall: 'warn',
    checks: [
      { id: 'ocr_readback', status: 'pass', value: 'A7-204914' },
      { id: 'seam', status: 'warn', value: 0.42, threshold: 0.35 },
    ],
  },
};

const TASK = {
  id: 't1',
  type: 'render',
  status: 'queued',
  progress: 0,
  message: null,
  error_code: null,
  subject_type: 'edit_job',
  subject_id: 'j1',
  created_at: '2026-10-20T10:00:00.000Z',
  started_at: null,
  finished_at: null,
};

describe('Editor', () => {
  it('shows the detected token and validates the new one before generating', async () => {
    const fetchMock = mockApi([
      ...base,
      { path: '/jobs/j1', body: { data: JOB } },
      { path: '/profiles/p1', body: { data: PROFILE } },
      { path: '/jobs/j1/render', method: 'POST', status: 202, body: { data: TASK } },
      { path: '/tasks/t1', body: { data: TASK } },
    ]);
    renderApp('/editor/j1');

    expect(
      await screen.findByRole('button', { name: /A7-204913/, pressed: true }),
    ).toBeInTheDocument();
    const generate = await screen.findByRole('button', { name: 'Generate' });
    expect(generate).toBeDisabled();

    const input = screen.getByLabelText('New token');
    fireEvent.change(input, { target: { value: 'A7-2049Q4' } });
    expect(await screen.findByText(/Not in this profile's character set/)).toBeInTheDocument();
    expect(generate).toBeDisabled();

    fireEvent.change(input, { target: { value: 'A7-204914' } });
    expect(generate).toBeEnabled();
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith('/jobs/j1/render') && init?.method === 'POST',
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ new_text: 'A7-204914' });
    });
  });

  it('shows the quality report and decision buttons after a render', async () => {
    mockApi([
      ...base,
      { path: '/jobs/j1', body: { data: RENDERED } },
      { path: '/profiles/p1', body: { data: PROFILE } },
    ]);
    renderApp('/editor/j1');

    const quality = await screen.findByRole('region', { name: 'Quality' });
    expect(quality).toHaveTextContent('OCR read-back');
    expect(quality).toHaveTextContent('A7-204914');
    expect(quality).toHaveTextContent('Warning');
    expect(screen.getByRole('button', { name: 'Accept' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled();
    expect(screen.getByRole('img', { name: 'Edited result' })).toHaveAttribute(
      'src',
      '/api/v1/files/f2',
    );
    expect(screen.getByRole('button', { name: /4s*This image/ })).toBeInTheDocument();
  });

  it('offers a manual region when no text was found', async () => {
    const fetchMock = mockApi([
      ...base,
      {
        path: '/jobs/j1',
        body: {
          data: {
            ...JOB,
            regions: [],
            selected_region_id: null,
            selected_quad: null,
            original_text: null,
            error_code: 'NO_TEXT_FOUND',
          },
        },
      },
      { path: '/profiles/p1', body: { data: PROFILE } },
      {
        path: '/jobs/j1/region',
        method: 'PUT',
        body: { data: { ...JOB, selected_region_id: null, original_text: null } },
      },
    ]);
    renderApp('/editor/j1');

    fireEvent.click(await screen.findByRole('button', { name: 'Draw region' }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT');
      expect(JSON.parse(String(call?.[1]?.body))).toHaveProperty('quad');
    });
    expect(await screen.findByText(/could not be read/)).toBeInTheDocument();
  });
});

describe('Home', () => {
  it('lists recent jobs and profile readiness', async () => {
    mockApi([
      ...base,
      { path: '/profiles', body: { data: [PROFILE] } },
      { path: '/jobs', body: { data: [RENDERED], meta: { next_cursor: null, count: 1 } } },
    ]);
    renderApp('/');

    const row = await screen.findByRole('row', { name: /A7-204913 → A7-204914/ });
    expect(row).toHaveTextContent('Needs review');
    expect(row).toHaveTextContent('Receipt token A');
    expect(screen.getByRole('link', { name: /Receipt token A/ })).toHaveTextContent(
      '100% coverage',
    );
    expect(screen.getByLabelText('Style Profile')).toHaveValue('p1');
  });

  it('guides first-time users without profiles', async () => {
    mockApi([
      ...base,
      { path: '/profiles', body: { data: [] } },
      { path: '/jobs', body: { data: [], meta: { next_cursor: null, count: 0 } } },
    ]);
    renderApp('/');

    expect(await screen.findByText('Three steps to your first edit')).toBeInTheDocument();
    expect(screen.getByText('Edits you start appear here.')).toBeInTheDocument();
  });
});
