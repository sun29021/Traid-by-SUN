import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';
import { type ReactNode, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  AdjustmentField,
  Badge,
  Banner,
  Button,
  MetricList,
  MetricRow,
  ProgressBar,
  TextField,
  TokenInput,
  validateToken,
} from '@/components';
import { getGlyphVariants } from '@/lib/api/jobs';
import { queryKeys } from '@/lib/api/queryKeys';
import type { EditJob, Profile, QualityCheck, Task } from '@/lib/api/types';

import styles from './Editor.module.css';
import { ADJUSTMENTS, changedCount, type EditorAction, type EditorState } from './editorStore';

const CHECK_LABELS: Record<string, string> = {
  ocr_readback: 'OCR read-back',
  seam: 'Seam',
  noise: 'Noise match',
  sharpness: 'Sharpness Δ',
  colour: 'Colour Δ',
  outside_unchanged: 'Outside unchanged',
};

const CHECK_UNITS: Record<string, string> = { sharpness: 'px', colour: 'ΔE' };

function checkValue(check: QualityCheck): string {
  if (check.id === 'outside_unchanged') return check.value ? 'Yes' : 'No';
  if (typeof check.value === 'number') return check.value.toFixed(check.id === 'colour' ? 1 : 2);
  if (check.value === '' || check.value === null) return '—';
  return String(check.value);
}

/** Focus target of the `T` shortcut. */
export const TOKEN_INPUT_ID = 'editor-new-token';

const SOURCE_LABEL = { same_image: 'This image', bank: 'Glyph bank', kept: 'Kept' } as const;

function Section({
  title,
  children,
  collapsible = false,
  defaultOpen = true,
  badge,
}: {
  title: string;
  children: ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
  badge?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const heading = collapsible ? (
    <button
      type="button"
      className={styles.sectionToggle}
      aria-expanded={open}
      onClick={() => setOpen(!open)}
    >
      {open ? <ChevronDown aria-hidden /> : <ChevronRight aria-hidden />}
      {title}
    </button>
  ) : (
    title
  );
  return (
    <section className={styles.section} aria-label={title}>
      <h2 className={styles.sectionTitle}>
        {heading}
        {badge}
      </h2>
      {(open || !collapsible) && <div className={styles.sectionBody}>{children}</div>}
    </section>
  );
}

export interface InspectorProps {
  job: EditJob;
  profile: Profile | undefined;
  newText: string;
  onNewText: (value: string) => void;
  state: EditorState;
  dispatch: (action: EditorAction) => void;
  renderTask: Task | undefined;
  busy: boolean;
  onGenerate: () => void;
  onAccept: () => void;
  onReject: () => void;
  onExport: () => void;
  onReopen: () => void;
  onFixOldText: (text: string) => void;
  onDrawRegion: () => void;
  exported: { url: string; name: string } | null;
  error: string | null;
}

export function Inspector(props: InspectorProps) {
  const { job, profile, state, dispatch } = props;
  const rendered = job.status === 'rendered' || job.status === 'rejected';
  const accepted = job.status === 'accepted';
  const finding = job.status === 'uploaded' || job.status === 'detecting';
  const rendering = job.status === 'rendering';
  const hasResult = Boolean(job.result);
  const validation = profile
    ? validateToken(props.newText, profile.charset, profile.token_pattern)
    : null;
  const canGenerate =
    Boolean(job.selected_quad && job.original_text && props.newText) &&
    validation !== null &&
    validation.invalidChars.length === 0 &&
    !(profile?.pattern_strict && validation.patternMatches === false) &&
    !accepted &&
    !props.busy;

  return (
    <aside className={styles.inspector} aria-label="Inspector">
      <Section title="Token">
        <dl className={styles.facts}>
          <dt>Profile</dt>
          <dd>{profile ? <Link to={`/profiles/${profile.id}`}>{profile.name}</Link> : '…'}</dd>
        </dl>
        {finding && <p className={styles.muted}>Finding text…</p>}
        {!finding && job.error_code === 'NO_TEXT_FOUND' && !job.selected_quad && (
          <Banner tone="warning" title="No text was found in this image.">
            Draw the region by hand, then type the old text.
            <div className={styles.inlineAction}>
              <Button onClick={props.onDrawRegion}>Draw region</Button>
            </div>
          </Banner>
        )}
        {job.selected_quad && (
          <OldText
            key={`${job.selected_region_id ?? 'drawn'}-${job.original_text ?? ''}`}
            value={job.original_text}
            disabled={accepted}
            onSave={props.onFixOldText}
          />
        )}
        {profile && (
          <TokenInput
            id={TOKEN_INPUT_ID}
            label="New token"
            value={props.newText}
            onChange={props.onNewText}
            charset={profile.charset}
            pattern={profile.token_pattern}
            disabled={accepted}
            helper="Ctrl+Enter generates"
          />
        )}
        {!hasResult && (
          <Button
            variant="primary"
            size="lg"
            onClick={props.onGenerate}
            disabled={!canGenerate}
            loading={rendering}
          >
            Generate
          </Button>
        )}
        {hasResult && !accepted && (
          <Button onClick={props.onGenerate} disabled={!canGenerate} loading={rendering}>
            Re-generate
          </Button>
        )}
        {rendering && (
          <ProgressBar
            label={props.renderTask?.message ?? 'Rendering'}
            value={props.renderTask ? props.renderTask.progress : undefined}
          />
        )}
        {props.error && <Banner tone="danger" title={props.error} />}
      </Section>

      <Section
        key={hasResult ? 'adjustments-ready' : 'adjustments'}
        title="Adjustments"
        collapsible
        defaultOpen={hasResult}
        badge={
          changedCount(state.params) > 0 ? (
            <Badge tone="info" label={`${changedCount(state.params)} changed`} />
          ) : undefined
        }
      >
        {ADJUSTMENTS.map((field) => (
          <AdjustmentField
            key={field.key}
            label={field.label}
            value={state.params[field.key] ?? 0}
            min={field.min}
            max={field.max}
            step={field.step}
            unit={field.unit}
            defaultValue={field.key === 'scale' || field.key === 'grain' ? 1 : 0}
            disabled={!hasResult || accepted}
            onChange={(value) => dispatch({ type: 'set', key: field.key, value })}
          />
        ))}
        <div className={styles.row}>
          <Button
            variant="ghost"
            icon={<RotateCcw aria-hidden />}
            disabled={!hasResult || accepted || changedCount(state.params) === 0}
            onClick={() => dispatch({ type: 'reset' })}
          >
            Reset all
          </Button>
          <span className={styles.muted}>Ctrl+Z / Ctrl+Shift+Z</span>
        </div>
      </Section>

      {job.glyphs_used.length > 0 && (
        <Section title="Characters" collapsible defaultOpen>
          <Characters job={job} state={state} dispatch={dispatch} disabled={accepted} />
        </Section>
      )}

      {job.quality && (
        <Section
          title="Quality"
          badge={
            <Badge
              tone={
                job.quality.overall === 'pass'
                  ? 'success'
                  : job.quality.overall === 'warn'
                    ? 'warning'
                    : 'danger'
              }
              label={
                job.quality.overall === 'pass'
                  ? 'Pass'
                  : job.quality.overall === 'warn'
                    ? 'Warning'
                    : 'Fail'
              }
            />
          }
        >
          <MetricList>
            {job.quality.checks.map((check) => (
              <MetricRow
                key={check.id}
                label={CHECK_LABELS[check.id] ?? check.id}
                value={checkValue(check)}
                {...(CHECK_UNITS[check.id] ? { unit: CHECK_UNITS[check.id] } : {})}
                status={check.status}
              />
            ))}
          </MetricList>
          {job.warnings.includes('INPAINT_FALLBACK_USED') && (
            <Banner tone="warning" title="Text removal used the simple fallback.">
              The learned remover is not installed; check Settings → Engine.
            </Banner>
          )}
        </Section>
      )}

      {(rendered || accepted) && (
        <Section title="Decision">
          {job.status === 'rendered' && (
            <div className={styles.row}>
              <Button variant="primary" size="lg" onClick={props.onAccept} disabled={props.busy}>
                Accept
              </Button>
              <Button onClick={props.onReject} disabled={props.busy}>
                Reject
              </Button>
            </div>
          )}
          {job.status === 'rejected' && (
            <p className={styles.muted}>Rejected. Adjust and re-generate, or change the token.</p>
          )}
          {accepted && (
            <>
              <div className={styles.row}>
                <Button variant="primary" size="lg" onClick={props.onExport} disabled={props.busy}>
                  Export
                </Button>
                <Button onClick={props.onReopen}>Edit again</Button>
              </div>
              {props.exported && (
                <p className={styles.muted}>
                  Exported.{' '}
                  <a href={props.exported.url} download={props.exported.name}>
                    Download {props.exported.name}
                  </a>
                </p>
              )}
            </>
          )}
        </Section>
      )}
    </aside>
  );
}

function OldText({
  value,
  disabled,
  onSave,
}: {
  value: string | null;
  disabled: boolean;
  onSave: (text: string) => void;
}) {
  const [editing, setEditing] = useState(value === null);
  const [draft, setDraft] = useState(value ?? '');
  if (!editing) {
    return (
      <dl className={styles.facts}>
        <dt>Old token</dt>
        <dd className={styles.mono}>
          {value}{' '}
          {!disabled && (
            <button type="button" className={styles.linkButton} onClick={() => setEditing(true)}>
              Not right? Edit
            </button>
          )}
        </dd>
      </dl>
    );
  }
  return (
    <form
      className={styles.oldTextForm}
      onSubmit={(event) => {
        event.preventDefault();
        if (draft.trim()) onSave(draft.trim());
        setEditing(false);
      }}
    >
      <TextField
        label="Old token"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        maxLength={64}
        helper={
          value === null
            ? 'The text could not be read. Type exactly what the image shows.'
            : undefined
        }
      />
      <Button type="submit" disabled={!draft.trim()}>
        Save old token
      </Button>
    </form>
  );
}

function Characters({
  job,
  state,
  dispatch,
  disabled,
}: {
  job: EditJob;
  state: EditorState;
  dispatch: (action: EditorAction) => void;
  disabled: boolean;
}) {
  const [position, setPosition] = useState<number | null>(null);
  const variants = useQuery({
    queryKey: queryKeys.glyphVariants(job.id, position ?? -1),
    queryFn: ({ signal }) => getGlyphVariants(job.id, position as number, signal),
    enabled: position !== null,
  });
  const overrides = state.params.glyph_overrides ?? {};
  return (
    <>
      <ul className={styles.chips} aria-label="Characters of the new token">
        {job.glyphs_used.map((use) => (
          <li key={use.position}>
            <button
              type="button"
              className={styles.chip}
              aria-pressed={position === use.position}
              disabled={use.source === 'kept' || disabled}
              onClick={() => setPosition(position === use.position ? null : use.position)}
              title={`${SOURCE_LABEL[use.source]}${use.score !== null ? ` · match ${Math.round(use.score * 100)}%` : ''}`}
            >
              <span className={styles.mono}>{use.char}</span>
              <span className={styles.chipSource} data-source={use.source}>
                {SOURCE_LABEL[use.source]}
              </span>
              {overrides[String(use.position)] && (
                <span className="visually-hidden">(chosen by you)</span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {position !== null && (
        <div className={styles.variants}>
          {variants.isPending && <p className={styles.muted}>Loading alternatives…</p>}
          {variants.data?.length === 0 && (
            <p className={styles.muted}>No other glyphs for this character.</p>
          )}
          <ul className={styles.variantList} aria-label="Alternative glyphs">
            {variants.data?.map((variant) => (
              <li key={variant.glyph_id ?? 'same'}>
                <button
                  type="button"
                  className={styles.variant}
                  aria-pressed={overrides[String(position)] === variant.glyph_id}
                  disabled={!variant.glyph_id}
                  onClick={() => {
                    dispatch({ type: 'override', position, glyphId: variant.glyph_id });
                    setPosition(null);
                  }}
                >
                  {variant.crop_url ? (
                    <img src={variant.crop_url} alt="" />
                  ) : (
                    <span className={styles.muted}>This image</span>
                  )}
                  <span className={styles.mono}>{Math.round(variant.score * 100)}%</span>
                </button>
              </li>
            ))}
          </ul>
          {overrides[String(position)] && (
            <Button
              variant="ghost"
              onClick={() => dispatch({ type: 'override', position, glyphId: null })}
            >
              Use the automatic choice
            </Button>
          )}
        </div>
      )}
    </>
  );
}
