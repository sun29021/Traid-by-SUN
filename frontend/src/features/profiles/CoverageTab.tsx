import { useNavigate } from 'react-router-dom';

import { Banner, Button, Skeleton } from '@/components';
import type { Profile } from '@/lib/api/types';

import styles from './Coverage.module.css';
import { displayChar } from './profileMeta';
import { useCoverage } from './useProfile';

/** Character coverage matrix (DESIGN.md §6.3, §11.4). Click a cell to review that character. */
export function CoverageTab({ profile }: { profile: Profile }) {
  const navigate = useNavigate();
  const coverage = useCoverage(profile.id);
  const need = profile.ready_threshold;

  if (coverage.isPending) return <Skeleton variant="block" height={200} />;
  if (coverage.isError) {
    return (
      <Banner
        tone="danger"
        title="Coverage could not be loaded."
        action={<Button onClick={() => void coverage.refetch()}>Retry</Button>}
      />
    );
  }
  return (
    <div className={styles.tab}>
      <p className={styles.rule}>
        Ready rule: every character needs at least {need} confirmed glyph{need === 1 ? '' : 's'}
        {profile.use_auto_glyphs ? ' (unreviewed glyphs count too)' : ''}. Spaces need none.
      </p>
      <ul className={styles.grid} aria-label="Character coverage">
        {coverage.data.map((item) => {
          const usable = item.confirmed + (profile.use_auto_glyphs ? item.auto : 0);
          const level = item.ready ? 'ready' : usable > 0 ? 'partial' : 'missing';
          return (
            <li key={item.char}>
              <button
                type="button"
                className={styles.cell}
                data-level={level}
                onClick={() =>
                  navigate(`/profiles/${profile.id}/glyphs?char=${encodeURIComponent(item.char)}`)
                }
              >
                <span className={styles.char}>{displayChar(item.char)}</span>
                <span className={styles.count}>
                  {item.confirmed}/{need}
                </span>
                {item.auto ? <span className={styles.auto}>+{item.auto}</span> : null}
                <span className="visually-hidden">{item.ready ? 'ready' : 'not ready'}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <dl className={styles.legend}>
        <div>
          <dt className={styles.swatch} data-level="ready" />
          <dd>Ready</dd>
        </div>
        <div>
          <dt className={styles.swatch} data-level="partial" />
          <dd>Some glyphs</dd>
        </div>
        <div>
          <dt className={styles.swatch} data-level="missing" />
          <dd>Missing</dd>
        </div>
        <div>
          <dt className={styles.autoLegend}>+n</dt>
          <dd>Waiting for review</dd>
        </div>
      </dl>
    </div>
  );
}
