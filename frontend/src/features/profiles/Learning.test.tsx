import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, noActiveTasks, okHealth, welcomeRoute } from '@/test/mockApi';
import { renderApp } from '@/test/renderApp';

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
    jobs_accepted: 3,
    acceptance_rate: 0.75,
  },
  learned_params: { dx: 1.95 },
  archived_at: null,
  created_at: '2026-10-20T10:00:00.000Z',
  updated_at: '2026-10-20T10:00:00.000Z',
};

const LEARNING = {
  accepted: 3,
  rejected: 1,
  acceptance_rate: 0.75,
  learned_params: { dx: 1.952, ink_tone: 0.244 },
  typical_region: { count: 3, cx: 0.5, cy: 0.5, sx: 0.01, sy: 0.01, w: 0.3, h: 0.05 },
  history: [
    { date: '2026-10-19', accepted: 1, rejected: 0 },
    { date: '2026-10-20', accepted: 2, rejected: 1 },
  ],
};

describe('Profile learning', () => {
  it('shows acceptance and the adjustments new edits start from', async () => {
    mockApi([
      okHealth,
      welcomeRoute(true),
      noActiveTasks,
      { path: '/profiles/p1', body: { data: PROFILE } },
      { path: '/profiles/p1/learning', body: { data: LEARNING } },
      { path: '/profiles/p1/coverage', body: { data: [] } },
    ]);
    renderApp('/profiles/p1');

    const panel = await screen.findByRole('region', { name: 'Learning' }, { timeout: 5000 });
    expect(panel).toHaveTextContent('Acceptance rate75%');
    expect(panel).toHaveTextContent('Last 14 days: 3 accepted, 1 rejected.');
    expect(panel).toHaveTextContent('Position x1.95');
    expect(panel).toHaveTextContent('Ink tone0.24');
  });
});
