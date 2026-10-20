import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { Banner, Button, MetricList, MetricRow } from '@/components';
import { getLearning } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { Learning, Profile } from '@/lib/api/types';

import { displayChar, PROFILE_STATUS } from './profileMeta';
import styles from './ProfileDetail.module.css';

function NextStep({ profile }: { profile: Profile }) {
  const navigate = useNavigate();
  const go = (tab: string) => navigate(`/profiles/${profile.id}/${tab}`);
  if (profile.status === 'training') {
    return <Banner tone="info" title="Extracting glyphs from your reference images…" />;
  }
  if (profile.stats.references === 0) {
    return (
      <Banner
        tone="info"
        title="Start by uploading real images of this text."
        action={
          <Button variant="primary" onClick={() => go('references')}>
            Upload references
          </Button>
        }
      >
        Different angles, lighting and textures help. Every character needs at least{' '}
        {profile.ready_threshold} good samples.
      </Banner>
    );
  }
  if (profile.stats.glyphs_auto > 0) {
    return (
      <Banner
        tone="warning"
        title={`${profile.stats.glyphs_auto} glyphs are waiting for your review.`}
        action={
          <Button variant="primary" onClick={() => go('glyphs')}>
            Review glyphs
          </Button>
        }
      >
        Only confirmed glyphs are used for edits
        {profile.use_auto_glyphs ? ' (auto glyphs are allowed for this profile)' : ''}.
      </Banner>
    );
  }
  if (profile.status === 'ready') {
    return (
      <Banner tone="info" title="This profile is ready.">
        Every character has enough confirmed glyphs. It can be used in the Editor.
      </Banner>
    );
  }
  return (
    <Banner
      tone="warning"
      title="Some characters have too few glyphs."
      action={<Button onClick={() => go('references')}>Add references</Button>}
    >
      Upload images that contain the missing characters listed below.
    </Banner>
  );
}

const PARAM_LABELS: Record<string, string> = {
  dx: 'Position x',
  dy: 'Position y',
  scale: 'Scale',
  spacing: 'Spacing',
  weight: 'Weight',
  blur: 'Blur',
  ink_tone: 'Ink tone',
  grain: 'Grain',
};

/** What accepted and rejected edits taught this profile (PRD FR-P05, US-52). */
function LearningPanel({ profileId }: { profileId: string }) {
  const learning = useQuery({
    queryKey: queryKeys.learning(profileId),
    queryFn: ({ signal }) => getLearning(profileId, signal),
  });
  const data: Learning | undefined = learning.data;
  if (!data) return null;
  const peak = Math.max(1, ...data.history.map((d) => d.accepted + d.rejected));
  const learned = Object.entries(data.learned_params);
  return (
    <section className={styles.panel} aria-labelledby="overview-learning">
      <h3 id="overview-learning" className={styles.sectionTitle}>
        Learning
      </h3>
      <MetricList>
        <MetricRow label="Accepted edits" value={data.accepted} />
        <MetricRow label="Rejected edits" value={data.rejected} />
        <MetricRow
          label="Acceptance rate"
          value={data.acceptance_rate === null ? '—' : `${Math.round(data.acceptance_rate * 100)}%`}
        />
      </MetricList>
      <figure className={styles.history}>
        <div className={styles.bars} aria-hidden>
          {data.history.map((day) => (
            <span
              key={day.date}
              className={styles.bar}
              title={`${day.date}: ${day.accepted} accepted, ${day.rejected} rejected`}
            >
              <span
                className={styles.barAccepted}
                style={{ height: `${(day.accepted / peak) * 100}%` }}
              />
              <span
                className={styles.barRejected}
                style={{ height: `${(day.rejected / peak) * 100}%` }}
              />
            </span>
          ))}
        </div>
        <figcaption className={styles.muted}>
          Last 14 days: {data.history.reduce((n, d) => n + d.accepted, 0)} accepted,{' '}
          {data.history.reduce((n, d) => n + d.rejected, 0)} rejected.
        </figcaption>
      </figure>
      {learned.length > 0 ? (
        <>
          <p className={styles.muted}>New edits start from your usual adjustments:</p>
          <MetricList>
            {learned.map(([key, value]) => (
              <MetricRow key={key} label={PARAM_LABELS[key] ?? key} value={value.toFixed(2)} />
            ))}
          </MetricList>
        </>
      ) : (
        <p className={styles.muted}>No adjustment habits learned yet.</p>
      )}
    </section>
  );
}

export function OverviewTab({ profile }: { profile: Profile }) {
  const { coverage, stats } = profile;
  return (
    <div className={styles.section}>
      <NextStep profile={profile} />
      <div className={styles.columns}>
        <section className={styles.panel} aria-labelledby="overview-numbers">
          <h3 id="overview-numbers" className={styles.sectionTitle}>
            Profile
          </h3>
          <MetricList>
            <MetricRow label="Status" value={PROFILE_STATUS[profile.status].label} />
            <MetricRow label="Reference images" value={stats.references} />
            <MetricRow label="Confirmed glyphs" value={stats.glyphs_confirmed} />
            <MetricRow label="Waiting for review" value={stats.glyphs_auto} />
            <MetricRow
              label="Characters covered"
              value={`${coverage.ready_chars} / ${coverage.total_chars}`}
              status={coverage.ready_chars === coverage.total_chars ? 'pass' : 'warn'}
            />
            <MetricRow label="Accepted edits" value={stats.jobs_accepted} />
          </MetricList>
        </section>
        <LearningPanel profileId={profile.id} />
        <section className={styles.panel} aria-labelledby="overview-missing">
          <h3 id="overview-missing" className={styles.sectionTitle}>
            Missing characters
          </h3>
          {coverage.missing.length === 0 ? (
            <p className={styles.muted}>None — every character is covered.</p>
          ) : (
            <>
              <p className={styles.missing}>{coverage.missing.map(displayChar).join(' ')}</p>
              <p className={styles.muted}>
                Each needs {profile.ready_threshold} confirmed glyph
                {profile.ready_threshold === 1 ? '' : 's'}.
              </p>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
