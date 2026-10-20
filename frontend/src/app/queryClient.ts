import { QueryClient } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/client';

const MAX_GET_RETRIES = 2;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Retry network failures only; API errors (4xx/5xx with an envelope) are final.
        retry: (failureCount, error) =>
          !(error instanceof ApiError) && failureCount < MAX_GET_RETRIES,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}
