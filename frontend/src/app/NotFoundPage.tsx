import { FileQuestion } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button, EmptyState } from '@/components';

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <EmptyState
      icon={<FileQuestion />}
      title="Page not found"
      description="This page does not exist or was moved."
      action={
        <Button variant="primary" onClick={() => navigate('/')}>
          Go to Home
        </Button>
      }
    />
  );
}
