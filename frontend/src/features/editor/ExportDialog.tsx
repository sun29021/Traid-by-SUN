import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';

import { Banner, Button, Checkbox, Dialog, Select, TextField } from '@/components';
import { exportJob } from '@/lib/api/jobs';
import { queryKeys } from '@/lib/api/queryKeys';
import { getSettings, updateSettings } from '@/lib/api/system';
import type { ExportRequest, ExportResult } from '@/lib/api/types';

import { downloadExport } from './download';
import styles from './ExportDialog.module.css';
import { messageFor } from './errors';

type Format = NonNullable<ExportRequest['format']>;

export interface ExportDialogProps {
  open: boolean;
  jobId: string;
  /** Suggested title, e.g. the new token. */
  suggestedTitle?: string | undefined;
  onClose: () => void;
  onExported: (result: ExportResult) => void;
}

function TextArea({
  label,
  value,
  onChange,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  maxLength: number;
}) {
  const id = useId();
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <textarea
        id={id}
        className={styles.textarea}
        value={value}
        maxLength={maxLength}
        rows={3}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

/**
 * Export with descriptive metadata (title, description, author, copyright, keywords,
 * comment). Capture data such as camera, date taken or location is never written.
 */
export function ExportDialog({
  open,
  jobId,
  suggestedTitle,
  onClose,
  onExported,
}: ExportDialogProps) {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: queryKeys.settings,
    queryFn: ({ signal }) => getSettings(signal),
    enabled: open,
  });
  const defaults = settings.data;
  const [format, setFormat] = useState<Format | ''>('');
  const [title, setTitle] = useState<string | null>(null);
  const [description, setDescription] = useState('');
  const [author, setAuthor] = useState<string | null>(null);
  const [copyright, setCopyright] = useState<string | null>(null);
  const [keywords, setKeywords] = useState('');
  const [comment, setComment] = useState('');
  const [remember, setRemember] = useState(false);

  const authorValue = author ?? String(defaults?.['export.default_author'] ?? '');
  const copyrightValue = copyright ?? String(defaults?.['export.default_copyright'] ?? '');
  const titleValue = title ?? suggestedTitle ?? '';

  const run = useMutation({
    mutationFn: async () => {
      if (remember) {
        const saved = await updateSettings({
          'export.default_author': authorValue.trim(),
          'export.default_copyright': copyrightValue.trim(),
        });
        queryClient.setQueryData(queryKeys.settings, saved);
      }
      return exportJob(jobId, {
        ...(format ? { format } : {}),
        metadata: {
          title: titleValue,
          description,
          author: authorValue,
          copyright: copyrightValue,
          keywords: keywords
            .split(/[,;]/)
            .map((k) => k.trim())
            .filter(Boolean)
            .slice(0, 30),
          comment,
        },
      });
    },
    onSuccess: (result) => {
      downloadExport(result);
      onExported(result);
      onClose();
    },
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Export"
      size="md"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={run.isPending} onClick={() => run.mutate()}>
            Export file
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        <Select
          label="Format"
          value={format}
          onChange={(event) => setFormat(event.target.value as Format | '')}
          options={[
            { value: '', label: 'Default from Settings' },
            { value: 'original', label: 'Same as the input' },
            { value: 'jpeg', label: 'JPEG' },
            { value: 'png', label: 'PNG' },
            { value: 'tiff', label: 'TIFF' },
          ]}
        />
        <h3 className={styles.heading}>Image details</h3>
        <TextField
          label="Title"
          value={titleValue}
          maxLength={300}
          onChange={(e) => setTitle(e.target.value)}
        />
        <TextArea
          label="Description"
          value={description}
          maxLength={2000}
          onChange={setDescription}
        />
        <div className={styles.row}>
          <TextField
            label="Author"
            value={authorValue}
            maxLength={300}
            onChange={(e) => setAuthor(e.target.value)}
          />
          <TextField
            label="Copyright"
            value={copyrightValue}
            maxLength={300}
            placeholder="© 2026 Your Name"
            onChange={(e) => setCopyright(e.target.value)}
          />
        </div>
        <Checkbox
          label="Remember author and copyright for next exports"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
        />
        <TextField
          label="Keywords"
          value={keywords}
          helper="Separate with commas."
          onChange={(e) => setKeywords(e.target.value)}
        />
        <TextArea label="Comment" value={comment} maxLength={2000} onChange={setComment} />
        <p className={styles.note}>
          Camera, date taken and location are not written into edited images. The file keeps
          Traid&apos;s &quot;edited&quot; marker unless it is turned off in Settings.
        </p>
        {run.isError && <Banner tone="danger" title={messageFor(run.error)} />}
      </div>
    </Dialog>
  );
}
