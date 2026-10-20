/**
 * The only HTTP client in the app (AGENTS.md §3). Parses API.md envelopes and
 * turns error envelopes into typed ApiError instances.
 */

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api/v1';

/**
 * Local request guard (ARCHITECTURE.md §7.1): the server only accepts changes that carry
 * this header. Other websites cannot send it, so they cannot change Traid's data.
 */
const CLIENT_HEADER = 'X-Traid-Client';
const CLIENT_HEADER_VALUE = 'web';
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

export interface ListMeta {
  next_cursor: string | null;
  count: number;
}

export interface ListResult<T> {
  items: T[];
  meta: ListMeta;
}

/** `?a=1&b=x` from defined values only; '' when nothing is set. */
export function queryString(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

/** Single-resource endpoints: resolves to the envelope's `data`. */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const payload = await send(path, options);
  return payload?.data as T;
}

/** List endpoints: resolves to the items plus pagination `meta` (API.md §1.5). */
export async function apiList<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ListResult<T>> {
  const payload = await send(path, options);
  return { items: (payload?.data ?? []) as T[], meta: payload?.meta as ListMeta };
}

async function send(
  path: string,
  options: RequestOptions,
): Promise<{ data: unknown; meta?: unknown } | undefined> {
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;

  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }
  if (MUTATING_METHODS.has(method)) {
    headers[CLIENT_HEADER] = CLIENT_HEADER_VALUE;
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
    return undefined;
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

  return payload;
}

function isDataEnvelope(value: unknown): value is { data: unknown; meta?: unknown } {
  return typeof value === 'object' && value !== null && 'data' in value;
}

/** True for the 403 the server sends until the Acceptable Use notice is acknowledged. */
export function isAupRequired(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 403 &&
    error.details?.['reason'] === 'aup_required'
  );
}
