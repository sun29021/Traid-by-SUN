import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { Badge, Button, type Column, Skeleton, Table, type Tone } from '@/components';
import { NewJob } from '@/features/editor/NewJob';
import { listJobs } from '@/lib/api/jobs';
import { listProfiles } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { EditJob, Profile } from '@/lib/api/types';
import { formatRelative } from '@/lib/format/time';

import styles from './Home.module.css';

const RECENT = 10;

const JOB_TONE: Record<EditJob['status'], Tone> = {
  uploaded: 'neutral',
  detecting: 'info',
  detected: 'neutral',
  rendering: 'info',
  rendered: 'warning',
  accepted: 'success',
  rejected: 'neutral',
  failed: 'danger',
};

const JOB_LABEL: Record<EditJob['status'], string> = {
  uploaded: 'Uploaded',
  detecting: 'Finding text',
  detected: 'Ready to edit',
  rendering: 'Rendering',
  rendered: 'Needs review',
  accepted: 'Accepted',
  rejected: 'Rejected',
  failed: 'Failed',
};

const PROFILE_TONE: Record<Profile['status'], Tone> = {
  ready: 'success',
  training: 'info',
  needs_review: 'warning',
  draft: 'neutral',
};

const PROFILE_LABEL: Record<Profile['status'], string> = {
  ready: 'Ready',
  training: 'Training',
  needs_review: 'Needs review',
  draft: 'Not ready',
};

export function HomePage() {
  const navigate = useNavigate();
  const jobs = useQuery({
    queryKey: queryKeys.jobList({ limit: RECENT }),
    queryFn: ({ signal }) => listJobs({ limit: RECENT }, signal),
  });
  const profiles = useQuery({
    queryKey: queryKeys.profileList('false'),
    queryFn: ({ signal }) => listProfiles({ archived: 'false' }, signal),
  });
  const names = new Map((profiles.data ?? []).map((p) => [p.id, p.name]));

  const columns: Column<EditJob>[] = [
    {
      key: 'thumb',
      header: 'Image',
      cell: (job) =>
        (job.result ?? job.input).thumb_url ? (
          <img
            className={styles.thumb}
            src={`${(job.result ?? job.input).thumb_url}?size=256`}
            alt=""
            loading="lazy"
          />
        ) : null,
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
    {
      key: 'status',
      header: 'Status',
      cell: (job) => <Badge tone={JOB_TONE[job.status]} label={JOB_LABEL[job.status]} />,
    },
    { key: 'time', header: 'Updated', cell: (job) => formatRelative(job.updated_at), align: 'end' },
  ];

  return (
    <div className={styles.home}>
      <div className={styles.main}>
        <NewJob />
        <section aria-labelledby="recent-jobs">
          <h2 id="recent-jobs" className={styles.heading}>
            Recent jobs
          </h2>
          {jobs.isPending && <Skeleton height={160} />}
          {jobs.data && jobs.data.items.length === 0 && (
            <p className={styles.muted}>Edits you start appear here.</p>
          )}
          {jobs.data && jobs.data.items.length > 0 && (
            <Table
              caption="Recent edit jobs"
              columns={columns}
              rows={jobs.data.items}
              rowKey={(job) => job.id}
              onRowClick={(job) => navigate(`/editor/${job.id}`)}
            />
          )}
        </section>
      </div>

      <aside className={styles.side} aria-labelledby="home-profiles">
        <div className={styles.sideHeader}>
          <h2 id="home-profiles" className={styles.heading}>
            Profiles
          </h2>
          <Button icon={<Plus aria-hidden />} onClick={() => navigate('/profiles?new=1')}>
            New profile
          </Button>
        </div>
        {profiles.isPending && <Skeleton height={120} />}
        <ul className={styles.profileList}>
          {(profiles.data ?? []).map((profile) => (
            <li key={profile.id}>
              <Link to={`/profiles/${profile.id}`} className={styles.profileRow}>
                <span className={styles.profileName}>{profile.name}</span>
                <span className={styles.profileMeta}>
                  <Badge
                    tone={PROFILE_TONE[profile.status]}
                    label={PROFILE_LABEL[profile.status]}
                  />
                  <span className={styles.muted}>
                    {profile.coverage.total_chars
                      ? `${Math.round((profile.coverage.ready_chars / profile.coverage.total_chars) * 100)}% coverage`
                      : 'No characters'}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {profiles.data?.length === 0 && (
          <p className={styles.muted}>Create a profile to teach Traid a token style.</p>
        )}
      </aside>
    </div>
  );
}
