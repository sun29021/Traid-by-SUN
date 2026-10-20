import { ApiError } from '@/lib/api/client';

/** Field messages from a 422 envelope, keyed by field path (API.md §1.4). */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.status !== 422) return {};
  const fields = (error.details?.['fields'] ?? []) as { path: string; message: string }[];
  const result: Record<string, string> = {};
  for (const field of fields) {
    if (!result[field.path]) result[field.path] = field.message;
  }
  return result;
}

export function errorCode(error: unknown): string | undefined {
  return error instanceof ApiError ? error.code : undefined;
}
