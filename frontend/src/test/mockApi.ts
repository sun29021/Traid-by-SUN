import { vi } from 'vitest';

type Body = Record<string, unknown> | null;

export interface MockRoute {
  method?: string;
  /** Path after /api/v1, matched without the query string, e.g. "/system/welcome". */
  path: string;
  status?: number;
  body: Body | ((request: { url: string; body: unknown }) => Body);
}

/**
 * Stub `fetch` with per-route JSON responses. Unknown routes return 404 so a test
 * fails loudly instead of hanging. Returns the mock to inspect calls.
 */
export function mockApi(routes: MockRoute[]) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const path = url.replace(/^.*\/api\/v1/, '').split('?')[0];
    const route = routes.find((r) => r.path === path && (r.method ?? 'GET') === method);
    if (!route) {
      return json(404, { error: { code: 'NOT_FOUND', message: `No mock for ${method} ${path}` } });
    }
    const body =
      typeof route.body === 'function'
        ? route.body({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
        : route.body;
    return json(route.status ?? 200, body);
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

function json(status: number, body: Body): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export const okHealth: MockRoute = {
  path: '/health',
  body: { data: { status: 'ok', version: '0.1.0' } },
};

export function welcomeRoute(accepted: boolean): MockRoute {
  return {
    path: '/system/welcome',
    body: { data: { aup_accepted: accepted, owner: { display_name: 'Xavier Sun' } } },
  };
}

export const noActiveTasks: MockRoute = {
  path: '/tasks',
  body: { data: [], meta: { next_cursor: null, count: 0 } },
};

export const systemStatus: MockRoute = {
  path: '/system/status',
  body: {
    data: {
      version: '0.1.0',
      schema_revision: '0003_local_owner',
      worker: { running: true, queued: 0 },
      storage: { data_dir: 'D:\\data', stored_bytes: 0, disk_free_bytes: 1, disk_total_bytes: 2 },
      engine: { ready: false, device: 'cpu', available_devices: ['cpu'], models: [] },
    },
  },
};
