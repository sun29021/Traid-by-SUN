import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { Banner, Button } from '@/components';
import { ApiError, NetworkError } from '@/lib/api/client';

import styles from './Welcome.module.css';
import { useWelcome } from './useWelcome';

/**
 * Sends the owner to the Welcome screen until the Acceptable Use notice is acknowledged
 * (PRD US-01). The server enforces the same rule; this only avoids a page of 403s.
 */
export function WelcomeGate() {
  const welcome = useWelcome();
  const location = useLocation();

  if (welcome.isPending) return null; // brief; avoids flashing the app before the redirect

  if (welcome.isError) {
    const offline = welcome.error instanceof NetworkError;
    return (
      <div className={styles.page}>
        <div className={styles.column}>
          <Banner
            tone="danger"
            title={offline ? 'Traid engine is not responding.' : 'Traid could not start.'}
            code={welcome.error instanceof ApiError ? welcome.error.code : undefined}
            action={
              <Button onClick={() => void welcome.refetch()} loading={welcome.isFetching}>
                Retry
              </Button>
            }
          >
            {offline
              ? 'Start it with scripts\\dev.ps1 or scripts\\start.ps1, then retry.'
              : welcome.error.message}
          </Banner>
        </div>
      </div>
    );
  }

  if (!welcome.data.aup_accepted) {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/welcome?next=${encodeURIComponent(next)}`} replace />;
  }

  return <Outlet />;
}
