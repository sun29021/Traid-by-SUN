import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, noActiveTasks, okHealth, systemStatus, welcomeRoute } from '@/test/mockApi';
import { renderApp } from '@/test/renderApp';

import { safeNextPath } from './useWelcome';

describe('Welcome', () => {
  it('redirects to Welcome until the Acceptable Use notice is accepted', async () => {
    mockApi([okHealth, systemStatus, noActiveTasks, welcomeRoute(false)]);
    const router = renderApp('/history');

    expect(await screen.findByRole('heading', { name: 'Traid' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/welcome');
    expect(router.state.location.search).toBe('?next=%2Fhistory');
  });

  it('shows engine checks and requires the checkbox before continuing', async () => {
    mockApi([okHealth, systemStatus, welcomeRoute(false)]);
    renderApp('/welcome');

    expect(await screen.findByText('Running · v0.1.0')).toBeInTheDocument();
    expect(await screen.findByText('Not installed yet')).toBeInTheDocument();
    expect(screen.getByText('Traid · Designed & developed by Xavier Sun')).toBeInTheDocument();

    const start = screen.getByRole('button', { name: 'Start using Traid' });
    expect(start).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(start).toBeEnabled();
  });

  it('accepting sends the client header and continues to the requested page', async () => {
    const fetchMock = mockApi([
      okHealth,
      systemStatus,
      noActiveTasks,
      welcomeRoute(false),
      {
        path: '/system/welcome',
        method: 'POST',
        body: { data: { aup_accepted: true, owner: { display_name: 'Xavier Sun' } } },
      },
    ]);
    const router = renderApp('/welcome?next=%2Fhistory');

    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Start using Traid' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/history'));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect((post?.[1]?.headers as Record<string, string>)['X-Traid-Client']).toBe('web');
  });

  it('only allows same-app paths after Welcome', () => {
    expect(safeNextPath('/profiles?tab=glyphs')).toBe('/profiles?tab=glyphs');
    expect(safeNextPath(null)).toBe('/');
    expect(safeNextPath('https://evil.example')).toBe('/');
    expect(safeNextPath('//evil.example')).toBe('/');
    expect(safeNextPath('/\\evil.example')).toBe('/');
    expect(safeNextPath('/welcome')).toBe('/');
  });
});
