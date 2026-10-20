import { ApiError } from '@/lib/api/client';

/** A sentence for an API error shown in the editor. */
export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'PROFILE_NOT_READY') {
      const missing = (error.details?.['missing'] ?? []) as string[];
      return `No reviewed glyphs for: ${missing.join(' ')}`;
    }
    return error.message;
  }
  return 'The request failed. Check that the engine is running.';
}
