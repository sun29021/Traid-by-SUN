import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiRequest, NetworkError } from './client';

function mockFetch(status: number, body: unknown) {
  // A fresh Response per call: a body can only be read once.
  const fn = vi.fn().mockImplementation(
    async () =>
      new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('apiRequest', () => {
  it('unwraps the data envelope', async () => {
    mockFetch(200, { data: { status: 'ok', version: '0.1.0' } });

    await expect(apiRequest('/health')).resolves.toEqual({ status: 'ok', version: '0.1.0' });
  });

  it('throws a typed ApiError from the error envelope', async () => {
    mockFetch(404, {
      error: { code: 'NOT_FOUND', message: 'Profile not found', request_id: 'abc' },
    });

    const error = await apiRequest('/profiles/x').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: 'NOT_FOUND', requestId: 'abc' });
  });

  it('sends the client header only on mutating requests', async () => {
    const fetchMock = mockFetch(200, { data: null });

    await apiRequest('/health');
    await apiRequest('/jobs', { method: 'POST', body: { a: 1 } });

    const getHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    const postHeaders = fetchMock.mock.calls[1]?.[1]?.headers as Record<string, string>;
    expect(getHeaders['X-Traid-Client']).toBeUndefined();
    expect(postHeaders['X-Traid-Client']).toBe('web');
  });

  it('treats a success response without a data envelope as an error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>', { status: 200 })));

    await expect(apiRequest('/health')).rejects.toMatchObject({ code: 'INTERNAL_ERROR' });
  });

  it('reports an unreachable server as NetworkError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    await expect(apiRequest('/health')).rejects.toBeInstanceOf(NetworkError);
  });
});
