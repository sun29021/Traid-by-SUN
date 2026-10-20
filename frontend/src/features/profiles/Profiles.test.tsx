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
  ready_threshold: 3,
  use_auto_glyphs: false,
  engine: 'glyph_transplant',
  status: 'needs_review',
  coverage: { ready_chars: 3, total_chars: 9, missing: ['A', '7'] },
  stats: {
    glyphs_confirmed: 4,
    glyphs_auto: 14,
    references: 2,
    jobs_accepted: 0,
    acceptance_rate: null,
  },
  learned_params: {},
  archived_at: null,
  created_at: '2026-10-20T10:00:00.000Z',
  updated_at: '2026-10-20T10:00:00.000Z',
};

describe('Profiles', () => {
  it('shows an empty state with a call to action', async () => {
    mockApi([...base, { path: '/profiles', body: { data: [] } }]);
    renderApp('/profiles');

    expect(await screen.findByText('No profiles yet')).toBeInTheDocument();
  });

  it('lists profiles with status, glyph counts and coverage', async () => {
    mockApi([...base, { path: '/profiles', body: { data: [PROFILE] } }]);
    renderApp('/profiles');

    const row = await screen.findByRole('row', { name: /Receipt token A/ });
    expect(row).toHaveTextContent('Needs review');
    expect(row).toHaveTextContent('4 / 18');
    expect(row).toHaveTextContent('33%');
  });

  it('requires a name and a surface type before creating', async () => {
    const fetchMock = mockApi([...base, { path: '/profiles', body: { data: [] } }]);
    renderApp('/profiles');
    fireEvent.click(
      (await screen.findAllByRole('button', { name: 'New profile' }))[0] as HTMLElement,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Create profile' }));

    expect(await screen.findByText('Give the profile a name')).toBeInTheDocument();
    expect(screen.getByText('Choose how the text was made')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  });

  it('creates a profile with the chosen surface and charset, then opens it', async () => {
    const fetchMock = mockApi([
      ...base,
      { path: '/profiles', body: { data: [] } },
      { path: '/profiles', method: 'POST', status: 201, body: { data: PROFILE } },
      { path: '/profiles/p1', body: { data: PROFILE } },
      {
        path: '/profiles/p1/references',
        body: { data: [], meta: { next_cursor: null, count: 0 } },
      },
    ]);
    const router = renderApp('/profiles');
    fireEvent.click(
      (await screen.findAllByRole('button', { name: 'New profile' }))[0] as HTMLElement,
    );

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Wall signs' } });
    fireEvent.click(screen.getByLabelText(/Paint/));
    fireEvent.change(screen.getByLabelText('Character set'), { target: { value: 'digits' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create profile' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/profiles/p1/references'));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      name: 'Wall signs',
      surface_type: 'paint',
      charset: '0123456789',
    });
  });

  it('shows the overview with the next step and missing characters', async () => {
    mockApi([...base, { path: '/profiles/p1', body: { data: PROFILE } }]);
    renderApp('/profiles/p1');

    expect(await screen.findByText('14 glyphs are waiting for your review.')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('A 7')).toBeInTheDocument();
  });

  it('shows not found for unknown profiles', async () => {
    mockApi([
      ...base,
      {
        path: '/profiles/nope',
        status: 404,
        body: { error: { code: 'NOT_FOUND', message: 'Profile not found' } },
      },
    ]);
    renderApp('/profiles/nope/overview');

    expect(await screen.findByText('Profile not found')).toBeInTheDocument();
  });
});
