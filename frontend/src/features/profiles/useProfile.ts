import { useQuery } from '@tanstack/react-query';

import { getCoverage, getProfile } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';

const TRAINING_POLL_MS = 1500;

/** A profile, refreshed while it is training so status and counts stay live. */
export function useProfile(profileId: string) {
  return useQuery({
    queryKey: queryKeys.profile(profileId),
    queryFn: ({ signal }) => getProfile(profileId, signal),
    refetchInterval: (query) =>
      query.state.data?.status === 'training' ? TRAINING_POLL_MS : false,
  });
}

export function useCoverage(profileId: string) {
  return useQuery({
    queryKey: queryKeys.coverage(profileId),
    queryFn: ({ signal }) => getCoverage(profileId, signal),
  });
}
