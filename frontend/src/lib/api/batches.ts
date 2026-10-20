import { apiRequest, queryString } from './client';
import type { Batch, BatchStarted, BatchValidation, EditJob, Task } from './types';

const id = encodeURIComponent;
const withSignal = (signal?: AbortSignal) => (signal ? { signal } : {});

export function validateBatch(
  body: { profile_id: string; template_job_id?: string | null; values: string[] },
  signal?: AbortSignal,
): Promise<BatchValidation> {
  return apiRequest<BatchValidation>('/batches/validate', {
    method: 'POST',
    body,
    ...withSignal(signal),
  });
}

export function createBatch(body: {
  template_job_id: string;
  values: string[];
  name?: string | null;
  client_request_id?: string | null;
}): Promise<BatchStarted> {
  return apiRequest<BatchStarted>('/batches', { method: 'POST', body });
}

export function listBatches(signal?: AbortSignal): Promise<Batch[]> {
  return apiRequest<Batch[]>(`/batches${queryString({ limit: 20 })}`, withSignal(signal));
}

export function getBatch(batchId: string, signal?: AbortSignal): Promise<Batch> {
  return apiRequest<Batch>(`/batches/${id(batchId)}`, withSignal(signal));
}

export function listBatchItems(batchId: string, signal?: AbortSignal): Promise<EditJob[]> {
  return apiRequest<EditJob[]>(`/batches/${id(batchId)}/items`, withSignal(signal));
}

export function cancelBatch(batchId: string): Promise<Batch> {
  return apiRequest<Batch>(`/batches/${id(batchId)}/cancel`, { method: 'POST' });
}

export function acceptPassed(batchId: string): Promise<{ accepted: number }> {
  return apiRequest<{ accepted: number }>(`/batches/${id(batchId)}/accept-passed`, {
    method: 'POST',
  });
}

export function exportBatch(batchId: string): Promise<Task> {
  return apiRequest<Task>(`/batches/${id(batchId)}/export`, { method: 'POST' });
}
