/**
 * The only HTTP client in the app (AGENTS.md §3). Parses API.md envelopes and
 * turns error envelopes into typed ApiError instances.
 */

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api/v1';

const CSRF_HEADER = 'X-Traid-CSRF';
const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;
  readonly requestId: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.request_id ?? null;
  }
}

/** Raised when the server cannot be reached at all (engine not running). */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('Traid engine is not responding.', { cause });
    this.name = 'NetworkError';
  }
}

let csrfToken: string | null = null;

/** Set after GET /auth/me (Phase 2). Sent on every state-changing request. */
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

function isErrorEnvelope(value: unknown): value is { error: ApiErrorBody } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error: unknown }).error === 'object'
  );
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;

  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }
  if (MUTATING_METHODS.has(method) && csrfToken) {
    headers[CSRF_HEADER] = csrfToken;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ?? null,
      credentials: 'same-origin',
      signal: options.signal ?? null,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new NetworkError(cause);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok && isErrorEnvelope(payload)) {
    throw new ApiError(response.status, payload.error);
  }
  if (!response.ok || !isDataEnvelope(payload)) {
    throw new ApiError(response.status, {
      code: 'INTERNAL_ERROR',
      message: `Unexpected response (${response.status})`,
      request_id: response.headers.get('X-Request-ID'),
    });
  }

  return payload.data as T;
}

function isDataEnvelope(value: unknown): value is { data: unknown } {
  return typeof value === 'object' && value !== null && 'data' in value;
}
