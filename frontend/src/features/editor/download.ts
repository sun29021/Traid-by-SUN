import type { ExportResult } from '@/lib/api/types';

/** Start a browser download of an exported file. */
export function downloadExport(result: ExportResult) {
  const link = document.createElement('a');
  link.href = `${result.file.url}?download=1`;
  link.download = result.download_name;
  document.body.append(link);
  link.click();
  link.remove();
}
