import { useQuery } from '@tanstack/react-query';

import { queryKeys } from '@/lib/api/queryKeys';
import { getWelcome } from '@/lib/api/system';

export function useWelcome() {
  return useQuery({
    queryKey: queryKeys.welcome,
    queryFn: ({ signal }) => getWelcome(signal),
    staleTime: Infinity, // only changes when the owner accepts, which updates the cache
  });
}

/**
 * Only same-app paths are allowed as a post-Welcome destination, so a crafted
 * `?next=//evil.example` can never redirect off-site.
 */
export function safeNextPath(next: string | null): string {
  // Backslashes and control characters are refused anywhere: browsers treat "\" like
  // "/", which enables open redirects (React Router advisory GHSA-wrjc-x8rr-h8h6).
  const unsafe = (c: string) => c === '\\' || c.charCodeAt(0) < 0x20 || c.charCodeAt(0) === 0x7f;
  if (!next || !next.startsWith('/') || next.startsWith('//') || [...next].some(unsafe)) {
    return '/';
  }
  return next.startsWith('/welcome') ? '/' : next;
}
