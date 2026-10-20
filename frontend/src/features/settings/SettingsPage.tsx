import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import {
  Badge,
  Banner,
  Button,
  type Column,
  MetricList,
  MetricRow,
  Select,
  Skeleton,
  Table,
  TabPanel,
  Tabs,
  TextField,
  Toggle,
  useToast,
} from '@/components';
import { messageFor } from '@/features/editor/errors';
import { queryKeys } from '@/lib/api/queryKeys';
import {
  getSettings,
  getSystemStatus,
  listAudit,
  listBackups,
  startBackup,
  updateSettings,
} from '@/lib/api/system';
import type { AuditEvent, Backup, Settings } from '@/lib/api/types';
import { deviceLabel } from '@/lib/format/device';
import { formatRelative } from '@/lib/format/time';
import { useTask } from '@/lib/hooks/useTask';

import { auditLabel } from './auditLabels';
import styles from './Settings.module.css';

const TABS = [
  { id: 'engine', label: 'Engine' },
  { id: 'export', label: 'Export' },
  { id: 'storage', label: 'Storage & backup' },
  { id: 'audit', label: 'Audit log' },
  { id: 'about', label: 'About' },
] as const;

type TabId = (typeof TABS)[number]['id'];

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unit]}`;
}

export function SettingsPage() {
  const { tab } = useParams();
  const navigate = useNavigate();
  const current: TabId = TABS.some((t) => t.id === tab) ? (tab as TabId) : 'engine';
  return (
    <div className={styles.page}>
      <Tabs
        label="Settings sections"
        idPrefix="settings"
        items={TABS}
        value={current}
        onChange={(id) => navigate(`/settings/${id}`)}
      />
      <TabPanel idPrefix="settings" id={current}>
        {current === 'engine' && <EngineTab />}
        {current === 'export' && <ExportTab />}
        {current === 'storage' && <StorageTab />}
        {current === 'audit' && <AuditTab />}
        {current === 'about' && <AboutTab />}
      </TabPanel>
    </div>
  );
}

function useStatus() {
  return useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: ({ signal }) => getSystemStatus(signal),
  });
}

function EngineTab() {
  const status = useStatus();
  if (!status.data)
    return status.isError ? (
      <Banner tone="danger" title="Status unavailable." />
    ) : (
      <Skeleton height={160} />
    );
  const { engine, worker, schema_revision: revision, version } = status.data;
  return (
    <section className={styles.panel} aria-labelledby="engine-title">
      <h2 id="engine-title" className={styles.heading}>
        Engine
      </h2>
      <MetricList>
        <MetricRow label="Traid version" value={version} />
        <MetricRow
          label="Database schema"
          value={revision ?? '—'}
          status={revision ? 'pass' : 'fail'}
        />
        <MetricRow
          label="Background worker"
          value={worker.running ? 'Running' : 'Stopped'}
          status={worker.running ? 'pass' : 'warn'}
        />
        <MetricRow label="Queued tasks" value={worker.queued} />
        <MetricRow label="Inference device" value={deviceLabel(engine.device)} />
        <MetricRow
          label="Available devices"
          value={engine.available_devices.map((d) => deviceLabel(d)).join(', ')}
        />
      </MetricList>
      <h3 className={styles.subheading}>Models</h3>
      <ul className={styles.models}>
        {engine.models.map((model) => (
          <li key={model.name}>
            <span className={styles.mono}>{model.name}</span>
            <span className={styles.muted}>{model.version}</span>
            <Badge
              tone={model.present && model.checksum_ok ? 'success' : 'warning'}
              label={
                model.present
                  ? model.checksum_ok
                    ? model.loaded
                      ? 'Loaded'
                      : 'Installed'
                    : 'Damaged'
                  : 'Missing'
              }
            />
          </li>
        ))}
      </ul>
      {!engine.ready && (
        <Banner tone="warning" title="Some required models are missing.">
          Run scripts\fetch_models.py (or scripts\setup.ps1) and restart Traid.
        </Banner>
      )}
    </section>
  );
}

function ExportTab() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const settings = useQuery({
    queryKey: queryKeys.settings,
    queryFn: ({ signal }) => getSettings(signal),
  });
  const [draft, setDraft] = useState<Settings | null>(null);
  const values = draft ?? settings.data ?? null;
  const save = useMutation({
    mutationFn: (changes: Settings) => updateSettings(changes),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.settings, data);
      setDraft(null);
      toast({ tone: 'success', message: 'Export settings saved' });
    },
  });
  if (!values) return <Skeleton height={200} />;
  const set = (key: string, value: unknown) => setDraft({ ...values, [key]: value });
  const quality = String(values['export.jpeg_quality_mode'] ?? 'match_source');
  const fixed = quality.startsWith('fixed:') ? quality.slice(6) : '92';
  return (
    <form
      className={styles.panel}
      aria-labelledby="export-title"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({
          'export.default_format': values['export.default_format'],
          'export.filename_pattern': values['export.filename_pattern'],
          'export.metadata_marker': values['export.metadata_marker'],
          'export.jpeg_quality_mode': values['export.jpeg_quality_mode'],
        });
      }}
    >
      <h2 id="export-title" className={styles.heading}>
        Export defaults
      </h2>
      <Select
        label="Default format"
        value={String(values['export.default_format'])}
        onChange={(e) => set('export.default_format', e.target.value)}
        options={[
          { value: 'original', label: 'Same as the input' },
          { value: 'jpeg', label: 'JPEG' },
          { value: 'png', label: 'PNG' },
          { value: 'tiff', label: 'TIFF' },
        ]}
      />
      <TextField
        label="File name pattern"
        value={String(values['export.filename_pattern'])}
        onChange={(e) => set('export.filename_pattern', e.target.value)}
        maxLength={120}
        helper="Tokens: {template} (input name), {token} (new value), {date}, {n}."
      />
      <Select
        label="JPEG quality"
        value={quality === 'match_source' ? 'match_source' : 'fixed'}
        onChange={(e) =>
          set(
            'export.jpeg_quality_mode',
            e.target.value === 'fixed' ? `fixed:${fixed}` : 'match_source',
          )
        }
        options={[
          { value: 'match_source', label: "Match the source photo's compression" },
          { value: 'fixed', label: 'Fixed quality' },
        ]}
      />
      {quality !== 'match_source' && (
        <TextField
          label="Fixed JPEG quality (60–100)"
          type="number"
          min={60}
          max={100}
          value={fixed}
          onChange={(e) => set('export.jpeg_quality_mode', `fixed:${e.target.value}`)}
        />
      )}
      <Toggle
        label="Mark exports as edited with Traid"
        checked={Boolean(values['export.metadata_marker'])}
        onChange={(e) => set('export.metadata_marker', e.target.checked)}
      />
      <p className={styles.muted}>Writes a note into the file's metadata (recommended).</p>
      {save.isError && <Banner tone="danger" title={messageFor(save.error)} />}
      <div className={styles.row}>
        <Button type="submit" variant="primary" loading={save.isPending} disabled={!draft}>
          Save export settings
        </Button>
        {draft && (
          <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
            Discard changes
          </Button>
        )}
      </div>
    </form>
  );
}

function StorageTab() {
  const queryClient = useQueryClient();
  const status = useStatus();
  const settings = useQuery({
    queryKey: queryKeys.settings,
    queryFn: ({ signal }) => getSettings(signal),
  });
  const backups = useQuery({
    queryKey: queryKeys.backups,
    queryFn: ({ signal }) => listBackups(signal),
  });
  const [taskId, setTaskId] = useState<string | null>(null);
  const { task, isPending } = useTask(taskId, [queryKeys.backups]);
  const start = useMutation({ mutationFn: startBackup, onSuccess: (t) => setTaskId(t.id) });
  const retention = useMutation({
    mutationFn: (value: number) => updateSettings({ 'storage.backup_retention': value }),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.settings, data),
  });
  const storage = status.data?.storage;
  const columns: Column<Backup>[] = [
    {
      key: 'name',
      header: 'Backup',
      cell: (b) => (
        <a href={b.download_url} download={b.name}>
          {b.name}
        </a>
      ),
    },
    {
      key: 'kind',
      header: 'Kind',
      cell: (b) => (b.kind === 'manual' ? 'Manual' : 'Before update'),
    },
    { key: 'size', header: 'Size', cell: (b) => bytes(b.byte_size), align: 'end' },
    { key: 'files', header: 'Files', cell: (b) => b.file_count, align: 'end' },
    {
      key: 'check',
      header: 'Integrity',
      cell: (b) => (
        <Badge
          tone={b.integrity_ok ? 'success' : b.integrity_ok === false ? 'danger' : 'neutral'}
          label={b.integrity_ok ? 'OK' : b.integrity_ok === false ? 'Failed' : 'Unknown'}
        />
      ),
    },
    { key: 'time', header: 'Created', cell: (b) => formatRelative(b.created_at), align: 'end' },
  ];
  return (
    <div className={styles.stack}>
      <section className={styles.panel} aria-labelledby="storage-title">
        <h2 id="storage-title" className={styles.heading}>
          Storage
        </h2>
        {storage ? (
          <MetricList>
            <MetricRow label="Data folder" value={storage.data_dir} />
            <MetricRow label="Stored by Traid" value={bytes(storage.stored_bytes)} />
            <MetricRow
              label="Free disk space"
              value={`${bytes(storage.disk_free_bytes)} of ${bytes(storage.disk_total_bytes)}`}
              status={
                storage.disk_free_bytes / Math.max(storage.disk_total_bytes, 1) < 0.05
                  ? 'warn'
                  : 'pass'
              }
            />
          </MetricList>
        ) : (
          <Skeleton height={80} />
        )}
      </section>
      <section className={styles.panel} aria-labelledby="backup-title">
        <div className={styles.row}>
          <h2 id="backup-title" className={styles.heading}>
            Backups
          </h2>
          <Button
            variant="primary"
            onClick={() => start.mutate()}
            loading={isPending || start.isPending}
          >
            Back up now
          </Button>
        </div>
        <p className={styles.muted}>
          A backup is a ZIP of the database and every stored image in data\backups. Traid never
          uploads it: copy it to an external drive yourself. Before each update Traid also backs up
          automatically.
        </p>
        {task?.status === 'failed' && <Banner tone="danger" title="The backup failed." />}
        {task?.status === 'succeeded' && (
          <Banner tone="info" title={task.message ?? 'Backup created'} />
        )}
        {settings.data && (
          <Select
            label="Manual backups to keep"
            value={String(settings.data['storage.backup_retention'])}
            onChange={(e) => retention.mutate(Number(e.target.value))}
            options={[1, 3, 5, 10, 20, 50].map((n) => ({ value: String(n), label: String(n) }))}
          />
        )}
        {backups.data && backups.data.length > 0 ? (
          <Table caption="Backups" columns={columns} rows={backups.data} rowKey={(b) => b.name} />
        ) : (
          <p className={styles.muted}>No backups yet.</p>
        )}
        <details className={styles.restore}>
          <summary>How to restore a backup</summary>
          <ol>
            <li>Stop Traid.</li>
            <li>Rename the data folder (for example to data-old).</li>
            <li>
              Create a new empty data folder and unzip the backup into it (it contains traid.db and
              files\).
            </li>
            <li>Start Traid. Settings → Engine shows the database schema once it is up.</li>
          </ol>
        </details>
      </section>
    </div>
  );
}

function AuditTab() {
  const [cursor, setCursor] = useState<string | null>(null);
  const [pages, setPages] = useState<AuditEvent[]>([]);
  const audit = useQuery({
    queryKey: queryKeys.audit({ cursor }),
    queryFn: ({ signal }) => listAudit({ cursor, limit: 50 }, signal),
  });
  const rows = [...pages, ...(audit.data?.items ?? [])];
  const columns: Column<AuditEvent>[] = [
    { key: 'time', header: 'When', cell: (e) => formatRelative(e.created_at) },
    { key: 'action', header: 'Action', cell: (e) => auditLabel(e.action) },
    {
      key: 'subject',
      header: 'Subject',
      cell: (e) => (e.subject_type ? `${e.subject_type} ${e.subject_id?.slice(0, 8) ?? ''}` : '—'),
    },
    {
      key: 'details',
      header: 'Details',
      cell: (e) => <span className={styles.mono}>{JSON.stringify(e.details)}</span>,
    },
  ];
  return (
    <section className={styles.panel} aria-labelledby="audit-title">
      <h2 id="audit-title" className={styles.heading}>
        Audit log
      </h2>
      <p className={styles.muted}>Every decision that changes data, newest first. Read-only.</p>
      {rows.length > 0 ? (
        <Table caption="Audit events" columns={columns} rows={rows} rowKey={(e) => e.id} />
      ) : (
        !audit.isPending && <p className={styles.muted}>Nothing recorded yet.</p>
      )}
      {audit.data?.meta.next_cursor && (
        <Button
          onClick={() => {
            setPages(rows);
            setCursor(audit.data?.meta.next_cursor ?? null);
          }}
        >
          Load more
        </Button>
      )}
    </section>
  );
}

function AboutTab() {
  const status = useStatus();
  return (
    <section className={styles.panel} aria-labelledby="about-title">
      <h2 id="about-title" className={styles.heading}>
        Traid {status.data ? `v${status.data.version}` : ''}
      </h2>
      <p>
        Replaces short text in photos with the real characters learned from your own reference
        images.
      </p>
      <p className={styles.credit}>Traid · Designed &amp; developed by Xavier Sun</p>
      <h3 className={styles.subheading}>Acceptable use</h3>
      <p className={styles.muted}>
        Edit only images you own or are authorised to change. Do not use Traid to forge documents,
        IDs, money, certificates or records, or to deceive anyone. Exports are marked as edited
        unless you turn that off.
      </p>
      <h3 className={styles.subheading}>Open-source models and libraries</h3>
      <ul className={styles.licenses}>
        <li>PP-OCRv4 detection and recognition (PaddleOCR, ONNX export by RapidAI) — Apache-2.0</li>
        <li>LaMa inpainting (advimman; ONNX by Carve, OpenCV Zoo) — Apache-2.0</li>
        <li>ONNX Runtime — MIT · OpenCV — Apache-2.0 · Pillow — MIT-CMU · NumPy — BSD-3-Clause</li>
        <li>
          FastAPI, SQLAlchemy, Alembic, Pydantic — MIT · React, TanStack Query — MIT · IBM Plex —
          OFL-1.1
        </li>
      </ul>
    </section>
  );
}
