import { apiList, apiRequest, type ListResult, queryString } from './client';
import type { AuditEvent, Backup, Health, Settings, SystemStatus, Task, Welcome } from './types';

export function getHealth(signal?: AbortSignal): Promise<Health> {
  return apiRequest<Health>('/health', signal ? { signal } : {});
}

export function getSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return apiRequest<SystemStatus>('/system/status', signal ? { signal } : {});
}

export function getWelcome(signal?: AbortSignal): Promise<Welcome> {
  return apiRequest<Welcome>('/system/welcome', signal ? { signal } : {});
}

export function acceptWelcome(): Promise<Welcome> {
  return apiRequest<Welcome>('/system/welcome', { method: 'POST', body: { accept_aup: true } });
}

export function getSettings(signal?: AbortSignal): Promise<Settings> {
  return apiRequest<Settings>('/settings', signal ? { signal } : {});
}

export function updateSettings(changes: Settings): Promise<Settings> {
  return apiRequest<Settings>('/settings', { method: 'PATCH', body: changes });
}

export function listBackups(signal?: AbortSignal): Promise<Backup[]> {
  return apiRequest<Backup[]>('/system/backups', signal ? { signal } : {});
}

export function startBackup(): Promise<Task> {
  return apiRequest<Task>('/system/backups', { method: 'POST' });
}

export function listAudit(
  params: { subjectId?: string; action?: string; cursor?: string | null; limit?: number } = {},
  signal?: AbortSignal,
): Promise<ListResult<AuditEvent>> {
  const query = queryString({
    subject_id: params.subjectId,
    action: params.action,
    cursor: params.cursor,
    limit: params.limit,
  });
  return apiList<AuditEvent>(`/audit${query}`, signal ? { signal } : {});
}
