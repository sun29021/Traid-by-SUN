import { apiList, apiRequest, type ListResult, queryString } from './client';
import type {
  BulkResult,
  CoverageItem,
  Glyph,
  GlyphBulk,
  GlyphStatus,
  Profile,
  ProfileCreate,
  ProfileUpdate,
  Reference,
  ReferenceChange,
  ReferenceStatus,
  ReferenceUpload,
  Task,
} from './types';

const id = encodeURIComponent;
const withSignal = (signal?: AbortSignal) => (signal ? { signal } : {});

// ---------------------------------------------------------------- profiles

export function listProfiles(
  params: { archived?: 'false' | 'true' | 'all'; q?: string } = {},
  signal?: AbortSignal,
): Promise<Profile[]> {
  const query = queryString({ archived: params.archived, q: params.q });
  return apiRequest<Profile[]>(`/profiles${query}`, withSignal(signal));
}

export function getProfile(profileId: string, signal?: AbortSignal): Promise<Profile> {
  return apiRequest<Profile>(`/profiles/${id(profileId)}`, withSignal(signal));
}

export function createProfile(body: ProfileCreate): Promise<Profile> {
  return apiRequest<Profile>('/profiles', { method: 'POST', body });
}

export function updateProfile(profileId: string, body: ProfileUpdate): Promise<Profile> {
  return apiRequest<Profile>(`/profiles/${id(profileId)}`, { method: 'PATCH', body });
}

export function setProfileArchived(profileId: string, archived: boolean): Promise<Profile> {
  const action = archived ? 'archive' : 'unarchive';
  return apiRequest<Profile>(`/profiles/${id(profileId)}/${action}`, { method: 'POST' });
}

export function deleteProfile(profileId: string, confirmName: string): Promise<undefined> {
  return apiRequest<undefined>(`/profiles/${id(profileId)}`, {
    method: 'DELETE',
    body: { confirm_name: confirmName },
  });
}

export function getCoverage(profileId: string, signal?: AbortSignal): Promise<CoverageItem[]> {
  return apiRequest<CoverageItem[]>(`/profiles/${id(profileId)}/coverage`, withSignal(signal));
}

// ---------------------------------------------------------------- reference images

export function listReferences(
  profileId: string,
  params: { status?: ReferenceStatus[]; cursor?: string | null; limit?: number } = {},
  signal?: AbortSignal,
): Promise<ListResult<Reference>> {
  const query = queryString({
    status: params.status?.join(','),
    cursor: params.cursor,
    limit: params.limit,
  });
  return apiList<Reference>(`/profiles/${id(profileId)}/references${query}`, withSignal(signal));
}

export function uploadReferences(
  profileId: string,
  files: File[],
  knownTexts: (string | null)[] = [],
): Promise<ReferenceUpload> {
  const form = new FormData();
  files.forEach((file, index) => {
    form.append('files', file, file.name);
    form.append('known_text', knownTexts[index] ?? '');
  });
  return apiRequest<ReferenceUpload>(`/profiles/${id(profileId)}/references`, {
    method: 'POST',
    body: form,
  });
}

export function setKnownText(
  referenceId: string,
  knownText: string | null,
): Promise<ReferenceChange> {
  return apiRequest<ReferenceChange>(`/references/${id(referenceId)}`, {
    method: 'PATCH',
    body: { known_text: knownText },
  });
}

export function reextractReference(referenceId: string): Promise<Task> {
  return apiRequest<Task>(`/references/${id(referenceId)}/reextract`, { method: 'POST' });
}

export function deleteReference(referenceId: string): Promise<undefined> {
  return apiRequest<undefined>(`/references/${id(referenceId)}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------- glyphs

export interface GlyphFilters {
  char?: string | undefined;
  status?: GlyphStatus[] | undefined;
  minQuality?: number | undefined;
}

const GLYPH_PAGE = 200;
const MAX_GLYPH_PAGES = 15; // 3000 glyphs per view is plenty for review

/** Every glyph matching the filters (follows cursors; the grid shows them all). */
export async function listAllGlyphs(
  profileId: string,
  filters: GlyphFilters = {},
  signal?: AbortSignal,
): Promise<Glyph[]> {
  const glyphs: Glyph[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MAX_GLYPH_PAGES; page += 1) {
    const query = queryString({
      char: filters.char,
      status: filters.status?.join(','),
      min_quality: filters.minQuality,
      limit: GLYPH_PAGE,
      cursor,
    });
    const result: ListResult<Glyph> = await apiList<Glyph>(
      `/profiles/${id(profileId)}/glyphs${query}`,
      withSignal(signal),
    );
    glyphs.push(...result.items);
    cursor = result.meta.next_cursor;
    if (!cursor) break;
  }
  return glyphs;
}

export function updateGlyph(
  glyphId: string,
  body: { status?: GlyphStatus; char?: string },
): Promise<Glyph> {
  return apiRequest<Glyph>(`/glyphs/${id(glyphId)}`, { method: 'PATCH', body });
}

export function bulkUpdateGlyphs(profileId: string, body: GlyphBulk): Promise<BulkResult> {
  return apiRequest<BulkResult>(`/profiles/${id(profileId)}/glyphs/bulk`, {
    method: 'POST',
    body,
  });
}
