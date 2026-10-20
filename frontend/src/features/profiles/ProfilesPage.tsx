import { useQuery } from '@tanstack/react-query';
import { Plus, SwatchBook } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  Badge,
  Banner,
  Button,
  type Column,
  EmptyState,
  Skeleton,
  Table,
  Toggle,
} from '@/components';
import { ApiError } from '@/lib/api/client';
import { listProfiles } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { Profile } from '@/lib/api/types';
import { formatRelative } from '@/lib/format/time';

import { CreateProfileDialog } from './CreateProfileDialog';
import { PROFILE_STATUS, surfaceLabel } from './profileMeta';
import styles from './Profiles.module.css';

const COLUMNS: Column<Profile>[] = [
  {
    key: 'name',
    header: 'Name',
    cell: (p) => (
      <span className={styles.nameCell}>
        <span className={styles.name}>{p.name}</span>
        {p.archived_at ? <span className={styles.chip}>Archived</span> : null}
      </span>
    ),
  },
  {
    key: 'surface',
    header: 'Surface',
    cell: (p) => <span className={styles.chip}>{surfaceLabel(p.surface_type)}</span>,
  },
  {
    key: 'status',
    header: 'Status',
    cell: (p) => (
      <Badge tone={PROFILE_STATUS[p.status].tone} label={PROFILE_STATUS[p.status].label} />
    ),
  },
  {
    key: 'glyphs',
    header: 'Glyphs',
    align: 'end',
    cell: (p) => `${p.stats.glyphs_confirmed} / ${p.stats.glyphs_confirmed + p.stats.glyphs_auto}`,
  },
  {
    key: 'coverage',
    header: 'Coverage',
    align: 'end',
    cell: (p) =>
      `${p.coverage.total_chars ? Math.round((100 * p.coverage.ready_chars) / p.coverage.total_chars) : 0}%`,
  },
  { key: 'updated', header: 'Updated', cell: (p) => formatRelative(p.updated_at) },
];

export function ProfilesPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const showArchived = params.get('archived') === 'all';
  const [creating, setCreating] = useState(params.get('new') === '1');

  const profiles = useQuery({
    queryKey: queryKeys.profileList(showArchived ? 'all' : 'false'),
    queryFn: ({ signal }) => listProfiles({ archived: showArchived ? 'all' : 'false' }, signal),
  });

  const toggleArchived = (checked: boolean) => {
    const next = new URLSearchParams(params);
    if (checked) next.set('archived', 'all');
    else next.delete('archived');
    setParams(next, { replace: true });
  };

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <p className={styles.lead}>
          A Style Profile learns one text style from your real photos: its glyphs, layout and
          surface.
        </p>
        <div className={styles.actions}>
          <Toggle
            label="Show archived"
            checked={showArchived}
            onChange={(e) => toggleArchived(e.target.checked)}
          />
          <Button variant="primary" icon={<Plus />} onClick={() => setCreating(true)}>
            New profile
          </Button>
        </div>
      </div>

      {profiles.isPending ? (
        <div className={styles.skeletons} aria-label="Loading profiles">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height={32} />
          ))}
        </div>
      ) : profiles.isError ? (
        <Banner
          tone="danger"
          title="Profiles could not be loaded."
          code={profiles.error instanceof ApiError ? profiles.error.code : undefined}
          action={<Button onClick={() => void profiles.refetch()}>Retry</Button>}
        />
      ) : profiles.data.length === 0 ? (
        <EmptyState
          icon={<SwatchBook />}
          title={showArchived ? 'No profiles' : 'No profiles yet'}
          description="Create a Style Profile, then upload real images of that text so Traid can learn its glyphs."
          action={
            <Button variant="primary" icon={<Plus />} onClick={() => setCreating(true)}>
              New profile
            </Button>
          }
        />
      ) : (
        <Table
          caption="Style Profiles"
          columns={COLUMNS}
          rows={profiles.data}
          rowKey={(p) => p.id}
          onRowClick={(p) => navigate(`/profiles/${p.id}`)}
        />
      )}

      {creating ? <CreateProfileDialog open onClose={() => setCreating(false)} /> : null}
    </div>
  );
}
