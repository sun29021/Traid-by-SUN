import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { mockApi, noActiveTasks, okHealth, systemStatus, welcomeRoute } from '@/test/mockApi';
import { renderApp } from '@/test/renderApp';

const base = [okHealth, welcomeRoute(true), noActiveTasks, systemStatus];

const SETTINGS = {
  'export.default_format': 'original',
  'export.filename_pattern': '{template}_{token}',
  'export.metadata_marker': true,
  'export.jpeg_quality_mode': 'match_source',
  'storage.backup_retention': 10,
};

describe('Settings', () => {
  it('saves export defaults and shows server validation errors', async () => {
    const fetchMock = mockApi([
      ...base,
      { path: '/settings', body: { data: SETTINGS } },
      {
        path: '/settings',
        method: 'PATCH',
        status: 422,
        body: {
          error: {
            code: 'VALIDATION_FAILED',
            message: 'Unknown token in the pattern: {secret}',
            details: {},
            request_id: null,
          },
        },
      },
    ]);
    renderApp('/settings/export');

    const pattern = await screen.findByLabelText('File name pattern');
    fireEvent.change(pattern, { target: { value: '{secret}' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save export settings' }));

    expect(await screen.findByText('Unknown token in the pattern: {secret}')).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      'export.filename_pattern': '{secret}',
    });
  });

  it('lists backups and starts a new one', async () => {
    const fetchMock = mockApi([
      ...base,
      { path: '/settings', body: { data: SETTINGS } },
      {
        path: '/system/backups',
        body: {
          data: [
            {
              name: 'traid-20261020-100000.zip',
              kind: 'manual',
              byte_size: 2048,
              created_at: '2026-10-20T10:00:00Z',
              schema_revision: '0005_edit_jobs',
              file_count: 12,
              integrity_ok: true,
              download_url: '/api/v1/system/backups/traid-20261020-100000.zip',
            },
          ],
        },
      },
      {
        path: '/system/backups',
        method: 'POST',
        status: 202,
        body: {
          data: {
            id: 't9',
            type: 'backup',
            status: 'queued',
            progress: 0,
            message: null,
            error_code: null,
            subject_type: 'system',
            subject_id: null,
            created_at: '2026-10-20T10:00:00.000Z',
            started_at: null,
            finished_at: null,
          },
        },
      },
      { path: '/tasks/t9', body: { data: { id: 't9', status: 'queued', progress: 0 } } },
    ]);
    renderApp('/settings/storage');

    const row = await screen.findByRole('row', { name: /traid-20261020-100000.zip/ });
    expect(row).toHaveTextContent('OK');
    expect(row).toHaveTextContent('2.0 KB');
    fireEvent.click(screen.getByRole('button', { name: 'Back up now' }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => String(url).endsWith('/system/backups') && init?.method === 'POST',
        ),
      ).toBe(true),
    );
  });

  it('credits the author on the About tab', async () => {
    mockApi([...base]);
    renderApp('/settings/about');

    expect(
      await screen.findByText('Traid · Designed & developed by Xavier Sun'),
    ).toBeInTheDocument();
  });
});
