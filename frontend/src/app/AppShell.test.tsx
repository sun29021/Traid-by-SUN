import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Providers } from './providers';
import { createQueryClient } from './queryClient';
import { routes } from './routes';

const HEALTH_BODY = JSON.stringify({ data: { status: 'ok', version: '0.1.0' } });

function renderAt(path: string) {
  // A fresh Response per call: a body can only be read once.
  const healthResponse = async () => new Response(HEALTH_BODY, { status: 200 });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(healthResponse));
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <Providers client={createQueryClient()}>
      <RouterProvider router={router} />
    </Providers>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('AppShell', () => {
  it('shows the credit and all primary navigation items', () => {
    renderAt('/');

    expect(screen.getByText('by Xavier Sun')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    for (const label of ['Home', 'Editor', 'Profiles', 'Batch', 'History', 'Settings']) {
      expect(nav).toHaveTextContent(label);
    }
  });

  it('uses the route title for the page heading and document title', () => {
    renderAt('/profiles');

    expect(screen.getByRole('heading', { level: 1, name: 'Style Profiles' })).toBeInTheDocument();
    expect(document.title).toBe('Style Profiles — Traid');
  });

  it('renders the not-found page for unknown routes', () => {
    renderAt('/nope');

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('reports the engine as online after a successful health check', async () => {
    renderAt('/');

    expect(await screen.findByText('Engine online · v0.1.0')).toBeInTheDocument();
  });
});
