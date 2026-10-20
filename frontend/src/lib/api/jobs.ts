import { apiList, apiRequest, type ListResult, queryString } from './client';
import type {
  EditJob,
  ExportRequest,
  ExportResult,
  GlyphVariant,
  JobCreated,
  JobStatus,
  QualityStatus,
  RegionUpdate,
  RenderParams,
  Task,
} from './types';

const id = encodeURIComponent;
const withSignal = (signal?: AbortSignal) => (signal ? { signal } : {});

export function createJob(profileId: string, file: File): Promise<JobCreated> {
  const form = new FormData();
  form.append('profile_id', profileId);
  form.append('file', file, file.name);
  return apiRequest<JobCreated>('/jobs', { method: 'POST', body: form });
}

export function getJob(jobId: string, signal?: AbortSignal): Promise<EditJob> {
  return apiRequest<EditJob>(`/jobs/${id(jobId)}`, withSignal(signal));
}

export interface JobFilters {
  profileId?: string | undefined;
  status?: JobStatus[] | undefined;
  quality?: QualityStatus[] | undefined;
  q?: string | undefined;
  from?: string | undefined;
  to?: string | undefined;
  cursor?: string | null | undefined;
  limit?: number | undefined;
}

export function listJobs(
  filters: JobFilters = {},
  signal?: AbortSignal,
): Promise<ListResult<EditJob>> {
  const query = queryString({
    profile_id: filters.profileId,
    status: filters.status?.join(','),
    quality: filters.quality?.join(','),
    q: filters.q,
    from: filters.from,
    to: filters.to,
    cursor: filters.cursor,
    limit: filters.limit,
  });
  return apiList<EditJob>(`/jobs${query}`, withSignal(signal));
}

export function setRegion(jobId: string, body: RegionUpdate): Promise<EditJob> {
  return apiRequest<EditJob>(`/jobs/${id(jobId)}/region`, { method: 'PUT', body });
}

export function renderJob(jobId: string, newText: string, params: RenderParams): Promise<Task> {
  return apiRequest<Task>(`/jobs/${id(jobId)}/render`, {
    method: 'POST',
    body: { new_text: newText, params },
  });
}

export function acceptJob(jobId: string): Promise<EditJob> {
  return apiRequest<EditJob>(`/jobs/${id(jobId)}/accept`, { method: 'POST' });
}

export function rejectJob(jobId: string, reason?: string): Promise<EditJob> {
  return apiRequest<EditJob>(`/jobs/${id(jobId)}/reject`, {
    method: 'POST',
    body: { reason: reason ?? null },
  });
}

export function exportJob(jobId: string, body: ExportRequest = {}): Promise<ExportResult> {
  return apiRequest<ExportResult>(`/jobs/${id(jobId)}/export`, { method: 'POST', body });
}

export function reopenJob(jobId: string): Promise<EditJob> {
  return apiRequest<EditJob>(`/jobs/${id(jobId)}/reopen`, { method: 'POST' });
}

export function deleteJob(jobId: string): Promise<undefined> {
  return apiRequest<undefined>(`/jobs/${id(jobId)}`, { method: 'DELETE' });
}

export function getGlyphVariants(
  jobId: string,
  position: number,
  signal?: AbortSignal,
): Promise<GlyphVariant[]> {
  return apiRequest<GlyphVariant[]>(
    `/jobs/${id(jobId)}/glyph-variants${queryString({ position })}`,
    withSignal(signal),
  );
}
