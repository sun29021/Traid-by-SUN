import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, noActiveTasks, okHealth, welcomeRoute } from '@/test/mockApi';
import { renderApp } from '@/test/renderApp';

const accepted = [okHealth, welcomeRoute(true), noActiveTasks];

describe('AppShell', () => {
  it('shows the credit and all primary navigation items', async () => {
    mockApi(accepted);
    renderApp('/');

    expect(await screen.findByText('by Xavier Sun')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    for (const label of ['Home', 'Editor', 'Profiles', 'Batch', 'History', 'Settings']) {
      expect(nav).toHaveTextContent(label);
    }
  });

  it('uses the route title for the page heading and document title', async () => {
    mockApi(accepted);
    renderApp('/profiles');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Style Profiles' }),
    ).toBeInTheDocument();
    expect(document.title).toBe('Style Profiles — Traid');
  });

  it('renders the not-found page for unknown routes', async () => {
    mockApi(accepted);
    renderApp('/nope');

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('reports the engine as online after a successful health check', async () => {
    mockApi(accepted);
    renderApp('/');

    expect(await screen.findByText('Engine online · v0.1.0')).toBeInTheDocument();
  });

  it('shows the offline banner when the engine stops answering', async () => {
    mockApi([welcomeRoute(true), noActiveTasks, { path: '/health', status: 500, body: null }]);
    renderApp('/');

    expect(await screen.findByText('Traid engine is not responding.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows running background tasks in the top bar', async () => {
    const task = {
      id: 't1',
      type: 'detect',
      subject_type: 'system',
      subject_id: null,
      status: 'running',
      progress: 0.4,
      message: null,
      error_code: null,
      created_at: '2026-10-20T10:00:00.000Z',
      started_at: null,
      finished_at: null,
    };
    mockApi([
      okHealth,
      welcomeRoute(true),
      { path: '/tasks', body: { data: [task], meta: { next_cursor: null, count: 1 } } },
    ]);
    renderApp('/');

    expect(await screen.findByText('1 task running')).toBeInTheDocument();
  });

  it('navigates with G-then-key shortcuts', async () => {
    mockApi(accepted);
    const router = renderApp('/');
    await screen.findByText('by Xavier Sun');

    fireEvent.keyDown(window, { key: 'g' });
    fireEvent.keyDown(window, { key: 'p' });

    await waitFor(() => expect(router.state.location.pathname).toBe('/profiles'));
  });
});
