import { type QueryKey, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { queryKeys } from '@/lib/api/queryKeys';
import { getTask } from '@/lib/api/tasks';
import type { Task } from '@/lib/api/types';

const POLL_MS = 500;

export function isActive(task: Task | undefined): boolean {
  return task?.status === 'queued' || task?.status === 'running';
}

/**
 * Follow a background task (ARCHITECTURE.md §4): poll every 500 ms while it is queued
 * or running, then invalidate `invalidate` so the affected data refreshes once.
 */
export function useTask(taskId: string | null | undefined, invalidate: QueryKey[] = []) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.task(taskId ?? 'none'),
    queryFn: ({ signal }) => getTask(taskId as string, signal),
    enabled: Boolean(taskId),
    refetchInterval: (q) => (isActive(q.state.data) || !q.state.data ? POLL_MS : false),
  });

  const settled = useRef<string | null>(null);
  const task = query.data;
  useEffect(() => {
    if (!task || isActive(task) || settled.current === task.id) return;
    settled.current = task.id;
    for (const key of invalidate) void queryClient.invalidateQueries({ queryKey: key });
    void queryClient.invalidateQueries({ queryKey: queryKeys.activeTasks });
    // `invalidate` is intentionally not a dependency: it is recreated every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task, queryClient]);

  return { task, isPending: Boolean(taskId) && (query.isPending || isActive(task)) };
}
