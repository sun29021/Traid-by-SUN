import { apiRequest } from './client';

export interface Health {
  status: 'ok';
  version: string;
}

export function getHealth(signal?: AbortSignal): Promise<Health> {
  return apiRequest<Health>('/health', signal ? { signal } : {});
}
