import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { ApiError, isAupRequired } from '@/lib/api/client';

const MAX_GET_RETRIES = 2;

export interface QueryClientOptions {
  /** Called when the server says the Acceptable Use notice must be acknowledged first. */
  onAupRequired?: () => void;
}

export function createQueryClient({ onAupRequired }: QueryClientOptions = {}): QueryClient {
  const handleError = (error: unknown) => {
    if (onAupRequired && isAupRequired(error)) onAupRequired();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleError }),
    mutationCache: new MutationCache({ onError: handleError }),
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
