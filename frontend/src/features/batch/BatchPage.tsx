import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Upload } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import {
  Badge,
  Banner,
  Button,
  Drawer,
  EmptyState,
  MetricList,
  MetricRow,
  ProgressBar,
  Select,
  TextField,
  type Tone,
  useToast,
} from '@/components';
import { messageFor } from '@/features/editor/errors';
import {
  acceptPassed,
  cancelBatch,
  createBatch,
  exportBatch,
  getBatch,
  listBatchItems,
  listBatches,
  validateBatch,
} from '@/lib/api/batches';
import { acceptJob, listJobs, rejectJob } from '@/lib/api/jobs';
import { queryKeys } from '@/lib/api/queryKeys';
import type { Batch, EditJob } from '@/lib/api/types';
import { useTask } from '@/lib/hooks/useTask';
import { formatRelative } from '@/lib/format/time';

import styles from './Batch.module.css';

const MAX_VALUES = 1000;
const POLL_MS = 1000;

const QUALITY_TONE: Record<string, Tone> = { pass: 'success', warn: 'warning', fail: 'danger' };
const QUALITY_LABEL: Record<string, string> = { pass: 'Pass', warn: 'Warning', fail: 'Fail' };
const STATUS_LABEL: Record<Batch['status'], string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  cancelled: 'Cancelled',
  failed: 'Failed',
};

function splitValues(text: string): string[] {
  return text
    .split(/\r?\n|,|;|\t/)
    .map((v) => v.trim())
    .filter(Boolean);
}

export function BatchPage() {
  const { batchId } = useParams();
  return batchId ? <BatchRun key={batchId} batchId={batchId} /> : <NewBatch />;
}

// ---------------------------------------------------------------- new batch

function NewBatch() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const templates = useQuery({
    queryKey: queryKeys.jobList({ status: ['rendered', 'accepted'], limit: 50 }),
    queryFn: ({ signal }) => listJobs({ status: ['rendered', 'accepted'], limit: 50 }, signal),
  });
  const previous = useQuery({
    queryKey: queryKeys.batches,
    queryFn: ({ signal }) => listBatches(signal),
  });
  const [chosen, setChosen] = useState<string>(params.get('template') ?? '');
  const [text, setText] = useState('');
  const [name, setName] = useState('');
  const [requestId] = useState(() => crypto.randomUUID());
  const items = templates.data?.items ?? [];
  const templateId = items.some((j) => j.id === chosen) ? chosen : (items[0]?.id ?? '');
  const template = items.find((j) => j.id === templateId);
  const values = useMemo(() => splitValues(text), [text]);

  // Live validation (debounced) of what the owner typed or imported.
  const [debounced, setDebounced] = useState<string[]>([]);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(values.slice(0, MAX_VALUES)), 300);
    return () => window.clearTimeout(timer);
  }, [values]);
  const validation = useQuery({
    queryKey: ['batches', 'validate', template?.profile_id, templateId, debounced],
    queryFn: ({ signal }) =>
      validateBatch(
        { profile_id: template?.profile_id ?? '', template_job_id: templateId, values: debounced },
        signal,
      ),
    enabled: Boolean(template) && debounced.length > 0,
  });

  const start = useMutation({
    mutationFn: () =>
      createBatch({
        template_job_id: templateId,
        values: validation.data?.valid ?? [],
        name: name.trim() || null,
        client_request_id: requestId,
      }),
    onSuccess: (started) => navigate(`/batch/${started.batch.id}`),
  });

  const importFile = async (file: File) => {
    const content = await file.text();
    setText((current) => (current ? `${current}\n${content}` : content));
  };

  if (templates.isSuccess && items.length === 0) {
    return (
      <EmptyState
        icon={<Upload />}
        title="Render one edit first"
        description="A batch reuses an edit's region and adjustments as its template. Open an image in the Editor, generate a result, then come back."
        action={
          <Button variant="primary" onClick={() => navigate('/editor')}>
            Open the Editor
          </Button>
        }
      />
    );
  }

  const valid = validation.data?.valid.length ?? 0;
  const tooMany = values.length > MAX_VALUES;
  return (
    <div className={styles.page}>
      <ol className={styles.steps} aria-label="Steps">
        <li data-active="true">Template</li>
        <li data-active={values.length > 0}>Values</li>
        <li>Run</li>
        <li>Review &amp; export</li>
      </ol>
      <div className={styles.columns}>
        <section className={styles.panel} aria-labelledby="batch-template">
          <h2 id="batch-template" className={styles.heading}>
            Template and values
          </h2>
          <Select
            label="Template edit"
            value={templateId}
            onChange={(event) => setChosen(event.target.value)}
            options={items.map((j) => ({
              value: j.id,
              label: `${j.original_text ?? '?'} → ${j.new_text ?? '?'} (${j.input.original_name ?? 'image'})`,
            }))}
            helper="Its image, region, adjustments and seed are used for every value."
          />
          <TextField
            label="Batch name (optional)"
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
          />
          <label className={styles.label} htmlFor="batch-values">
            Token values — one per line
          </label>
          <textarea
            id="batch-values"
            className={styles.values}
            value={text}
            onChange={(event) => setText(event.target.value)}
            spellCheck={false}
            rows={12}
          />
          <div className={styles.row}>
            <label className={styles.importButton}>
              <Upload aria-hidden /> Import CSV/TXT
              <input
                type="file"
                accept=".csv,.txt,text/plain,text/csv"
                className="visually-hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void importFile(file);
                  event.target.value = '';
                }}
              />
            </label>
            <span className={styles.muted}>
              {values.length} value{values.length === 1 ? '' : 's'} (max {MAX_VALUES})
            </span>
          </div>
        </section>

        <section className={styles.panel} aria-labelledby="batch-check" aria-live="polite">
          <h2 id="batch-check" className={styles.heading}>
            Check
          </h2>
          {tooMany && <Banner tone="danger" title={`At most ${MAX_VALUES} values per batch.`} />}
          {values.length === 0 && <p className={styles.muted}>Add token values to start.</p>}
          {validation.data && (
            <>
              <MetricList>
                <MetricRow label="Valid" value={validation.data.valid.length} status="pass" />
                <MetricRow
                  label="Invalid"
                  value={validation.data.invalid.length}
                  {...(validation.data.invalid.length ? { status: 'fail' as const } : {})}
                />
                <MetricRow label="Duplicates (skipped)" value={validation.data.duplicates.length} />
              </MetricList>
              {validation.data.invalid.length > 0 && (
                <ul className={styles.invalidList} aria-label="Invalid values">
                  {validation.data.invalid.map((item) => (
                    <li key={item.value}>
                      <span className={styles.mono}>{item.value}</span> — {item.message}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          {start.isError && <Banner tone="danger" title={messageFor(start.error)} />}
          <Button
            variant="primary"
            size="lg"
            disabled={
              !valid || tooMany || (validation.data?.invalid.length ?? 0) > 0 || start.isPending
            }
            loading={start.isPending}
            onClick={() => start.mutate()}
          >
            {valid ? `Run batch (${valid})` : 'Run batch'}
          </Button>
          {(validation.data?.invalid.length ?? 0) > 0 && (
            <p className={styles.muted}>Fix or remove the invalid values to start.</p>
          )}
        </section>
      </div>

      {(previous.data?.length ?? 0) > 0 && (
        <section aria-labelledby="batch-previous">
          <h2 id="batch-previous" className={styles.heading}>
            Previous batches
          </h2>
          <ul className={styles.previous}>
            {previous.data?.map((batch) => (
              <li key={batch.id}>
                <Link to={`/batch/${batch.id}`}>
                  {batch.name ?? `Batch of ${batch.total_count}`}
                </Link>
                <Badge
                  tone={batch.status === 'completed' ? 'success' : 'neutral'}
                  label={STATUS_LABEL[batch.status]}
                />
                <span className={styles.muted}>{formatRelative(batch.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- run and review

/** The current time, refreshed every second while `active` (for the ETA). */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function BatchRun({ batchId }: { batchId: string }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const batch = useQuery({
    queryKey: queryKeys.batch(batchId),
    queryFn: ({ signal }) => getBatch(batchId, signal),
    refetchInterval: (q) =>
      q.state.data && (q.state.data.status === 'queued' || q.state.data.status === 'running')
        ? POLL_MS
        : false,
  });
  const running = batch.data?.status === 'queued' || batch.data?.status === 'running';
  const items = useQuery({
    queryKey: queryKeys.batchItems(batchId),
    queryFn: ({ signal }) => listBatchItems(batchId, signal),
    refetchInterval: running ? POLL_MS * 2 : false,
  });
  const [openId, setOpenId] = useState<string | null>(null);
  const [exportTaskId, setExportTaskId] = useState<string | null>(null);
  const { task: exportTask, isPending: exporting } = useTask(exportTaskId, [
    queryKeys.batch(batchId),
  ]);
  const [startedAt] = useState(() => Date.now());
  const now = useNow(running);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.batch(batchId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.batchItems(batchId) });
  };
  const cancel = useMutation({ mutationFn: () => cancelBatch(batchId), onSuccess: refresh });
  const acceptAll = useMutation({
    mutationFn: () => acceptPassed(batchId),
    onSuccess: (result) => {
      toast({ tone: 'success', message: `${result.accepted} items accepted` });
      refresh();
    },
  });
  const exporter = useMutation({
    mutationFn: () => exportBatch(batchId),
    onSuccess: (task) => setExportTaskId(task.id),
    onError: (error) => toast({ tone: 'danger', message: messageFor(error) }),
  });

  if (!batch.data) {
    return batch.isError ? <Banner tone="danger" title="This batch could not be loaded." /> : null;
  }
  const { counts, total_count: total } = batch.data;
  const done = total - counts.pending;
  const elapsed = (now - startedAt) / 1000;
  const eta = running && done > 0 ? Math.round((elapsed / done) * counts.pending) : null;
  const open = items.data?.find((j) => j.id === openId) ?? null;

  return (
    <div className={styles.page}>
      <ol className={styles.steps} aria-label="Steps">
        <li>Template</li>
        <li>Values</li>
        <li data-active={running}>Run</li>
        <li data-active={!running}>Review &amp; export</li>
      </ol>
      <header className={styles.runHeader}>
        <div>
          <h2 className={styles.heading}>{batch.data.name ?? `Batch of ${total}`}</h2>
          <Badge
            tone={
              batch.data.status === 'completed'
                ? 'success'
                : batch.data.status === 'cancelled'
                  ? 'warning'
                  : 'info'
            }
            label={STATUS_LABEL[batch.data.status]}
          />
        </div>
        <div className={styles.row}>
          {running && (
            <Button onClick={() => cancel.mutate()} loading={cancel.isPending}>
              Cancel
            </Button>
          )}
          <Button
            onClick={() => acceptAll.mutate()}
            disabled={running || counts.rendered === 0}
            loading={acceptAll.isPending}
          >
            Accept all passed ({counts.rendered})
          </Button>
          <Button
            variant="primary"
            onClick={() => exporter.mutate()}
            disabled={counts.accepted === 0 || exporting}
            loading={exporting}
          >
            Export accepted ({counts.accepted})
          </Button>
        </div>
      </header>

      {running && (
        <ProgressBar
          value={total ? done / total : 0}
          label={`${done} of ${total} rendered${eta !== null ? ` · about ${eta} s left` : ''}`}
        />
      )}
      <p className={styles.muted}>
        {counts.rendered} passed · {counts.warn} with warnings · {counts.failed} failed ·{' '}
        {counts.accepted} accepted · {counts.rejected} rejected
      </p>
      {batch.data.export_file && !exporting && (
        <Banner tone="info" title="The ZIP is ready.">
          <a
            href={`${batch.data.export_file.url}?download=1`}
            download={batch.data.export_file.original_name ?? 'batch.zip'}
          >
            Download {batch.data.export_file.original_name}
          </a>
        </Banner>
      )}
      {exportTask?.status === 'failed' && <Banner tone="danger" title="The export failed." />}

      <ul className={styles.grid} aria-label="Batch items, warnings first">
        {items.data?.map((job) => (
          <li key={job.id}>
            <button type="button" className={styles.item} onClick={() => setOpenId(job.id)}>
              {job.result?.thumb_url ? (
                <img src={`${job.result.thumb_url}?size=256`} alt="" loading="lazy" />
              ) : (
                <span className={styles.placeholder}>
                  {job.status === 'failed' ? 'Failed' : 'Waiting'}
                </span>
              )}
              <span className={styles.mono}>{job.new_text}</span>
              <span className={styles.itemMeta}>
                {job.quality ? (
                  <Badge
                    tone={QUALITY_TONE[job.quality.overall] ?? 'neutral'}
                    label={QUALITY_LABEL[job.quality.overall] ?? ''}
                  />
                ) : (
                  <Badge
                    tone={job.status === 'failed' ? 'danger' : 'neutral'}
                    label={job.status === 'failed' ? 'Failed' : 'Pending'}
                  />
                )}
                {job.status === 'accepted' && <Badge tone="success" label="Accepted" />}
                {job.status === 'rejected' && <Badge tone="neutral" label="Rejected" />}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <ItemDrawer job={open} onClose={() => setOpenId(null)} onChanged={refresh} />
    </div>
  );
}

function ItemDrawer({
  job,
  onClose,
  onChanged,
}: {
  job: EditJob | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const decide = useMutation({
    mutationFn: (action: 'accept' | 'reject') =>
      action === 'accept' ? acceptJob(job?.id ?? '') : rejectJob(job?.id ?? ''),
    onSuccess: () => {
      onChanged();
      onClose();
    },
  });
  return (
    <Drawer
      open={job !== null}
      onClose={onClose}
      title={job ? `Item ${job.new_text ?? ''}` : 'Item'}
    >
      {job && (
        <div className={styles.drawer}>
          <figure className={styles.compare}>
            <img src={job.input.url} alt="Original image" />
            <figcaption className={styles.muted}>Original</figcaption>
          </figure>
          {job.result && (
            <figure className={styles.compare}>
              <img src={job.result.url} alt="Edited result" />
              <figcaption className={styles.muted}>Result</figcaption>
            </figure>
          )}
          {job.quality && (
            <MetricList>
              {job.quality.checks.map((check) => (
                <MetricRow
                  key={check.id}
                  label={check.id.replace(/_/g, ' ')}
                  value={String(check.value ?? '—')}
                  status={check.status}
                />
              ))}
            </MetricList>
          )}
          {job.error_code && <Banner tone="danger" title={`Failed: ${job.error_code}`} />}
          <div className={styles.row}>
            {job.status === 'rendered' && (
              <>
                <Button
                  variant="primary"
                  onClick={() => decide.mutate('accept')}
                  loading={decide.isPending}
                >
                  Accept
                </Button>
                <Button onClick={() => decide.mutate('reject')} disabled={decide.isPending}>
                  Reject
                </Button>
              </>
            )}
            <Link to={`/editor/${job.id}`}>Open in the Editor to adjust</Link>
          </div>
        </div>
      )}
    </Drawer>
  );
}
