import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderClock } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import {
  Badge,
  Banner,
  Button,
  type Column,
  Dialog,
  EmptyState,
  MetricList,
  MetricRow,
  Select,
  Skeleton,
  Table,
  TextField,
  type Tone,
  useToast,
} from '@/components';
import { messageFor } from '@/features/editor/errors';
import { auditLabel } from '@/features/settings/auditLabels';
import { deleteJob, exportJob, getJob, type JobFilters, listJobs, reopenJob } from '@/lib/api/jobs';
import { listProfiles } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import { listAudit } from '@/lib/api/system';
import type { EditJob, JobStatus, QualityStatus } from '@/lib/api/types';
import { formatRelative } from '@/lib/format/time';

import styles from './History.module.css';

const PAGE = 25;

const STATUS: Record<JobStatus, { label: string; tone: Tone }> = {
  uploaded: { label: 'Uploaded', tone: 'neutral' },
  detecting: { label: 'Finding text', tone: 'info' },
  detected: { label: 'Ready to edit', tone: 'neutral' },
  rendering: { label: 'Rendering', tone: 'info' },
  rendered: { label: 'Needs review', tone: 'warning' },
  accepted: { label: 'Accepted', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'neutral' },
  failed: { label: 'Failed', tone: 'danger' },
};

const QUALITY: Record<QualityStatus, { label: string; tone: Tone }> = {
  pass: { label: 'Pass', tone: 'success' },
  warn: { label: 'Warning', tone: 'warning' },
  fail: { label: 'Fail', tone: 'danger' },
};

export function HistoryPage() {
  const { jobId } = useParams();
  return jobId ? <JobDetail key={jobId} jobId={jobId} /> : <HistoryList />;
}

function HistoryList() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filters: JobFilters = {
    profileId: params.get('profile') ?? undefined,
    status:
      (params.get('status')?.split(',').filter(Boolean) as JobStatus[] | undefined) ?? undefined,
    quality:
      (params.get('quality')?.split(',').filter(Boolean) as QualityStatus[] | undefined) ??
      undefined,
    q: params.get('q') ?? undefined,
    from: params.get('from') ?? undefined,
    to: params.get('to') ?? undefined,
    limit: PAGE,
  };
  const profiles = useQuery({
    queryKey: queryKeys.profileList('all'),
    queryFn: ({ signal }) => listProfiles({ archived: 'all' }, signal),
  });
  const jobs = useInfiniteQuery({
    queryKey: queryKeys.jobList(filters),
    queryFn: ({ pageParam, signal }) => listJobs({ ...filters, cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.meta.next_cursor,
  });
  const [search, setSearch] = useState(filters.q ?? '');
  const names = new Map((profiles.data ?? []).map((p) => [p.id, p.name]));
  const rows = jobs.data?.pages.flatMap((p) => p.items) ?? [];

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const columns: Column<EditJob>[] = [
    {
      key: 'thumb',
      header: 'Image',
      cell: (job) => {
        const ref = job.result ?? job.input;
        return ref.thumb_url ? (
          <img className={styles.thumb} src={`${ref.thumb_url}?size=256`} alt="" loading="lazy" />
        ) : null;
      },
    },
    {
      key: 'token',
      header: 'Token',
      cell: (job) => (
        <span className={styles.mono}>
          {job.original_text ?? '—'}
          {job.new_text ? ` → ${job.new_text}` : ''}
        </span>
      ),
    },
    { key: 'profile', header: 'Profile', cell: (job) => names.get(job.profile_id) ?? '…' },
    { key: 'status', header: 'Status', cell: (job) => <Badge {...STATUS[job.status]} /> },
    {
      key: 'quality',
      header: 'Quality',
      cell: (job) => (job.quality ? <Badge {...QUALITY[job.quality.overall]} /> : '—'),
    },
    { key: 'time', header: 'Updated', cell: (job) => formatRelative(job.updated_at), align: 'end' },
  ];

  return (
    <div className={styles.page}>
      <form
        className={styles.filters}
        role="search"
        aria-label="Filter history"
        onSubmit={(event) => {
          event.preventDefault();
          setFilter('q', search.trim());
        }}
      >
        <TextField
          label="Token starts with"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          maxLength={64}
        />
        <Select
          label="Profile"
          value={filters.profileId ?? ''}
          onChange={(e) => setFilter('profile', e.target.value)}
          options={[
            { value: '', label: 'All profiles' },
            ...(profiles.data ?? []).map((p) => ({ value: p.id, label: p.name })),
          ]}
        />
        <Select
          label="Status"
          value={params.get('status') ?? ''}
          onChange={(e) => setFilter('status', e.target.value)}
          options={[
            { value: '', label: 'Any status' },
            { value: 'accepted', label: 'Accepted' },
            { value: 'rendered', label: 'Needs review' },
            { value: 'rejected', label: 'Rejected' },
            { value: 'detected,uploaded', label: 'Not rendered' },
            { value: 'failed', label: 'Failed' },
          ]}
        />
        <Select
          label="Quality"
          value={params.get('quality') ?? ''}
          onChange={(e) => setFilter('quality', e.target.value)}
          options={[
            { value: '', label: 'Any quality' },
            { value: 'pass', label: 'Pass' },
            { value: 'warn', label: 'Warning' },
            { value: 'fail', label: 'Fail' },
          ]}
        />
        <TextField
          label="From"
          type="date"
          value={filters.from ?? ''}
          onChange={(e) => setFilter('from', e.target.value)}
        />
        <TextField
          label="To"
          type="date"
          value={filters.to ?? ''}
          onChange={(e) => setFilter('to', e.target.value)}
        />
        <Button type="submit">Search</Button>
      </form>

      {jobs.isPending && <Skeleton height={240} />}
      {jobs.isError && <Banner tone="danger" title={messageFor(jobs.error)} />}
      {jobs.isSuccess && rows.length === 0 && (
        <EmptyState
          icon={<FolderClock />}
          title={params.toString() ? 'No edits match these filters' : 'No edits yet'}
          description="Every image you open in the Editor appears here, with its result and quality report."
        />
      )}
      {rows.length > 0 && (
        <Table
          caption="Edit history"
          columns={columns}
          rows={rows}
          rowKey={(job) => job.id}
          onRowClick={(job) => navigate(`/history/${job.id}`)}
        />
      )}
      {jobs.hasNextPage && (
        <Button onClick={() => void jobs.fetchNextPage()} loading={jobs.isFetchingNextPage}>
          Load more
        </Button>
      )}
    </div>
  );
}

function JobDetail({ jobId }: { jobId: string }) {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const job = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: ({ signal }) => getJob(jobId, signal),
  });
  const audit = useQuery({
    queryKey: queryKeys.audit({ subjectId: jobId }),
    queryFn: ({ signal }) => listAudit({ subjectId: jobId, limit: 50 }, signal),
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const exporter = useMutation({
    mutationFn: () => exportJob(jobId),
    onSuccess: (result) => {
      const link = document.createElement('a');
      link.href = `${result.file.url}?download=1`;
      link.download = result.download_name;
      document.body.append(link);
      link.click();
      link.remove();
      void queryClient.invalidateQueries({ queryKey: queryKeys.job(jobId) });
    },
    onError: (error) => toast({ tone: 'danger', message: messageFor(error) }),
  });
  const reopen = useMutation({
    mutationFn: () => reopenJob(jobId),
    onSuccess: (copy) => navigate(`/editor/${copy.id}`),
  });
  const remove = useMutation({
    mutationFn: () => deleteJob(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      toast({ tone: 'success', message: 'Edit deleted' });
      navigate('/history');
    },
    onError: (error) => toast({ tone: 'danger', message: messageFor(error) }),
  });

  if (!job.data)
    return job.isError ? (
      <Banner tone="danger" title="This edit could not be loaded." />
    ) : (
      <Skeleton height={320} />
    );
  const data = job.data;
  const params = Object.entries(data.params).filter(([key]) => key !== 'glyph_overrides');

  return (
    <div className={styles.page}>
      <div className={styles.detailHeader}>
        <Link to="/history">← History</Link>
        <h2 className={styles.heading}>
          <span className={styles.mono}>
            {data.original_text ?? '—'}
            {data.new_text ? ` → ${data.new_text}` : ''}
          </span>
        </h2>
        <Badge {...STATUS[data.status]} />
        <div className={styles.actions}>
          {data.status === 'accepted' && (
            <Button
              variant="primary"
              onClick={() => exporter.mutate()}
              loading={exporter.isPending}
            >
              Export again
            </Button>
          )}
          {data.status === 'accepted' ? (
            <Button onClick={() => reopen.mutate()}>Edit a copy</Button>
          ) : (
            <Button onClick={() => navigate(`/editor/${data.id}`)}>Open in the Editor</Button>
          )}
          <Button variant="danger" onClick={() => setConfirmDelete(true)}>
            Delete
          </Button>
        </div>
      </div>

      <div className={styles.compare}>
        <figure>
          <img src={data.input.url} alt="Original image" />
          <figcaption className={styles.muted}>Original · {data.input.original_name}</figcaption>
        </figure>
        {data.result && (
          <figure>
            <img src={data.result.url} alt="Edited result" />
            <figcaption className={styles.muted}>Result</figcaption>
          </figure>
        )}
      </div>

      <div className={styles.columns}>
        <section className={styles.panel} aria-labelledby="detail-quality">
          <h3 id="detail-quality" className={styles.heading}>
            Quality
          </h3>
          {data.quality ? (
            <MetricList>
              {data.quality.checks.map((check) => (
                <MetricRow
                  key={check.id}
                  label={check.id.replace(/_/g, ' ')}
                  value={String(check.value ?? '—')}
                  status={check.status}
                />
              ))}
            </MetricList>
          ) : (
            <p className={styles.muted}>Not rendered.</p>
          )}
          {data.reject_reason && <p className={styles.muted}>Rejected: {data.reject_reason}</p>}
        </section>
        <section className={styles.panel} aria-labelledby="detail-params">
          <h3 id="detail-params" className={styles.heading}>
            Adjustments
          </h3>
          <MetricList>
            {params.map(([key, value]) => (
              <MetricRow key={key} label={key.replace(/_/g, ' ')} value={String(value)} />
            ))}
            <MetricRow label="Layout" value={data.layout_mode ?? '—'} />
            <MetricRow label="Engine" value={data.engine_version ?? '—'} />
            <MetricRow label="Seed" value={data.seed} />
          </MetricList>
        </section>
        <section className={styles.panel} aria-labelledby="detail-audit">
          <h3 id="detail-audit" className={styles.heading}>
            Activity
          </h3>
          <ul className={styles.timeline}>
            <li>
              Created <span className={styles.muted}>{formatRelative(data.created_at)}</span>
            </li>
            {(audit.data?.items ?? []).map((event) => (
              <li key={event.id}>
                {auditLabel(event.action)}{' '}
                <span className={styles.muted}>{formatRelative(event.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Delete this edit?"
        size="sm"
        footer={
          <>
            <Button onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              Delete edit
            </Button>
          </>
        }
      >
        <p>
          The edit and its result disappear from History. Exported files you saved are not affected.
        </p>
      </Dialog>
    </div>
  );
}
