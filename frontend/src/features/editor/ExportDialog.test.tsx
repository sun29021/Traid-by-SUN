import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '@/components';
import { mockApi } from '@/test/mockApi';

import { ExportDialog } from './ExportDialog';

// jsdom cannot follow a download link; the click itself is browser behaviour.
vi.mock('./download', () => ({ downloadExport: vi.fn() }));

const SETTINGS = {
  'export.default_format': 'original',
  'export.filename_pattern': '{template}_{token}',
  'export.metadata_marker': true,
  'export.jpeg_quality_mode': 'match_source',
  'storage.backup_retention': 10,
  'export.default_author': 'Xavier Sun',
  'export.default_copyright': '© 2026 Xavier Sun',
};

const EXPORTED = {
  file: {
    id: 'f9',
    url: '/api/v1/files/f9',
    thumb_url: null,
    mime_type: 'image/jpeg',
    width: 10,
    height: 10,
    byte_size: 100,
    original_name: 'receipt_A7-204914.jpg',
  },
  download_name: 'receipt_A7-204914.jpg',
};

describe('ExportDialog', () => {
  it('prefills defaults and sends the image details', async () => {
    const fetchMock = mockApi([
      { path: '/settings', body: { data: SETTINGS } },
      { path: '/jobs/j1/export', method: 'POST', status: 201, body: { data: EXPORTED } },
    ]);
    const onExported = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ToastProvider>
          <ExportDialog
            open
            jobId="j1"
            suggestedTitle="A7-204914"
            onClose={() => {}}
            onExported={onExported}
          />
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByDisplayValue('Xavier Sun')).toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toHaveValue('A7-204914');
    fireEvent.change(screen.getByLabelText('Keywords'), { target: { value: 'traid, receipt,, ' } });
    fireEvent.change(screen.getByLabelText('Format'), { target: { value: 'png' } });
    fireEvent.click(screen.getByRole('button', { name: 'Export file' }));

    await waitFor(() => expect(onExported).toHaveBeenCalledWith(EXPORTED));
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/jobs/j1/export'));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      format: 'png',
      metadata: {
        title: 'A7-204914',
        description: '',
        author: 'Xavier Sun',
        copyright: '© 2026 Xavier Sun',
        keywords: ['traid', 'receipt'],
        comment: '',
      },
    });
    expect(screen.queryByLabelText(/camera|date taken|location/i)).not.toBeInTheDocument();
  });
});
