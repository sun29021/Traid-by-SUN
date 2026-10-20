import { FileQuestion } from 'lucide-react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';

import { Badge, Banner, Button, EmptyState, Skeleton, TabPanel, Tabs } from '@/components';
import { ApiError } from '@/lib/api/client';

import { CoverageTab } from './CoverageTab';
import { GlyphsTab } from './GlyphsTab';
import { OverviewTab } from './OverviewTab';
import { PROFILE_STATUS, surfaceLabel } from './profileMeta';
import styles from './ProfileDetail.module.css';
import { ReferencesTab } from './ReferencesTab';
import { SettingsTab } from './SettingsTab';
import { useProfile } from './useProfile';

const PROFILE_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'references', label: 'References' },
  { id: 'glyphs', label: 'Glyphs' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'settings', label: 'Settings' },
] as const;
type TabId = (typeof PROFILE_TABS)[number]['id'];

function isTab(value: string | undefined): value is TabId {
  return PROFILE_TABS.some((tab) => tab.id === value);
}

/** Profile detail with URL tabs: /profiles/:profileId/:tab (DESIGN.md §11.4). */
export function ProfileDetailPage() {
  const { profileId = '', tab } = useParams();
  const navigate = useNavigate();
  const profile = useProfile(profileId);

  if (!isTab(tab)) return <Navigate to={`/profiles/${profileId}/overview`} replace />;

  if (profile.isPending) {
    return (
      <div className={styles.page} aria-label="Loading profile">
        <Skeleton width="40%" height={28} />
        <Skeleton variant="block" height={240} />
      </div>
    );
  }
  if (profile.isError) {
    if (profile.error instanceof ApiError && profile.error.status === 404) {
      return (
        <EmptyState
          icon={<FileQuestion />}
          title="Profile not found"
          description="It may have been deleted."
          action={<Button onClick={() => navigate('/profiles')}>Back to profiles</Button>}
        />
      );
    }
    return (
      <Banner
        tone="danger"
        title="This profile could not be loaded."
        code={profile.error instanceof ApiError ? profile.error.code : undefined}
        action={<Button onClick={() => void profile.refetch()}>Retry</Button>}
      />
    );
  }

  const data = profile.data;
  const status = PROFILE_STATUS[data.status];
  return (
    <div className={styles.page}>
      <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
        <Link to="/profiles">Style Profiles</Link>
        <span aria-hidden>/</span>
        <span aria-current="page">{data.name}</span>
      </nav>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h2 className={styles.title}>{data.name}</h2>
          <Badge tone={status.tone} label={status.label} />
          <span className={styles.chip}>{surfaceLabel(data.surface_type)}</span>
          {data.archived_at ? <span className={styles.chip}>Archived</span> : null}
        </div>
        {data.description ? <p className={styles.description}>{data.description}</p> : null}
      </header>
      {data.archived_at ? (
        <Banner tone="info" title="This profile is archived.">
          It is read-only. Restore it in Settings to add references or edit it.
        </Banner>
      ) : null}

      <div>
        <Tabs
          label="Profile sections"
          idPrefix="profile"
          items={PROFILE_TABS}
          value={tab}
          onChange={(next) => navigate(`/profiles/${profileId}/${next}`)}
        />
        <TabPanel idPrefix="profile" id={tab}>
          {tab === 'overview' ? <OverviewTab profile={data} /> : null}
          {tab === 'references' ? <ReferencesTab profile={data} /> : null}
          {tab === 'glyphs' ? <GlyphsTab profile={data} /> : null}
          {tab === 'coverage' ? <CoverageTab profile={data} /> : null}
          {tab === 'settings' ? <SettingsTab profile={data} /> : null}
        </TabPanel>
      </div>
    </div>
  );
}
