import { apiRequest } from './client';
import type { Health, SystemStatus, Welcome } from './types';

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
