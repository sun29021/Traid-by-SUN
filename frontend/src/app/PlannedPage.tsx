import type { LucideIcon } from 'lucide-react';

import { EmptyState } from '@/components';

interface PlannedPageProps {
  icon: LucideIcon;
  title: string;
  description: string;
  phase: string;
}

/** Placeholder for routes whose feature lands in a later phase (IMPLEMENTATION_PLAN.md). */
export function PlannedPage({ icon: Icon, title, description, phase }: PlannedPageProps) {
  return (
    <EmptyState
      icon={<Icon />}
      title={`${title} is not built yet`}
      description={`${description} Planned for ${phase}.`}
    />
  );
}
