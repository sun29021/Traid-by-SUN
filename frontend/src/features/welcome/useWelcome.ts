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
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) {
    return '/';
  }
  return next.startsWith('/welcome') ? '/' : next;
}
