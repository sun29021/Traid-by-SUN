import { apiList, apiRequest, type ListResult, queryString } from './client';
import type { Task, TaskStatus } from './types';

export interface TaskListParams {
  /** Defaults to active tasks (queued, running) on the server. */
  status?: TaskStatus[];
  cursor?: string | null;
  limit?: number;
}

export function listTasks(
  params: TaskListParams = {},
  signal?: AbortSignal,
): Promise<ListResult<Task>> {
  const query = queryString({
    status: params.status?.join(','),
    cursor: params.cursor,
    limit: params.limit,
  });
  return apiList<Task>(`/tasks${query}`, signal ? { signal } : {});
}

export function getTask(taskId: string, signal?: AbortSignal): Promise<Task> {
  return apiRequest<Task>(`/tasks/${encodeURIComponent(taskId)}`, signal ? { signal } : {});
}

export function cancelTask(taskId: string): Promise<Task> {
  return apiRequest<Task>(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
}

export function retryTask(taskId: string): Promise<Task> {
  return apiRequest<Task>(`/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' });
}
