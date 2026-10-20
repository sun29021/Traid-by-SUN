import { TriangleAlert } from 'lucide-react';
import { useNavigate, useRouteError } from 'react-router-dom';

import { Button, EmptyState } from '@/components';

/** Recoverable error panel when a page crashes while rendering (ARCHITECTURE.md §13). */
export function RouteErrorPage() {
  const error = useRouteError();
  const navigate = useNavigate();
  const message = error instanceof Error ? error.message : 'Unexpected error';
  return (
    <EmptyState
      icon={<TriangleAlert />}
      title="Something went wrong on this page"
      description={`${message}. Your data is safe; reload the page or go back to Home.`}
      action={
        <Button variant="primary" onClick={() => navigate('/')}>
          Go to Home
        </Button>
      }
    />
  );
}
