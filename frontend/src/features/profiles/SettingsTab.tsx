import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  Banner,
  Button,
  Checkbox,
  Dialog,
  Select,
  TextField,
  Toggle,
  useToast,
} from '@/components';
import { ApiError } from '@/lib/api/client';
import { deleteProfile, setProfileArchived, updateProfile } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { Profile, ProfileUpdate } from '@/lib/api/types';

import { errorCode, fieldErrors } from './errors';
import { CHARSET_PRESETS, type CharsetPresetId, presetFor } from './profileMeta';
import styles from './ProfileDetail.module.css';
import { SurfaceTypePicker } from './SurfaceTypePicker';

const ALIGNMENTS = [
  { value: 'auto', label: 'Automatic' },
  { value: 'left', label: 'Left' },
  { value: 'center', label: 'Centre' },
  { value: 'right', label: 'Right' },
];
const SPACING = [
  { value: 'auto', label: 'Automatic' },
  { value: 'monospace', label: 'Monospace (fixed pitch)' },
  { value: 'proportional', label: 'Proportional' },
];

function SettingsForm({ profile }: { profile: Profile }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState({
    name: profile.name,
    description: profile.description ?? '',
    surface_type: profile.surface_type,
    preset: presetFor(profile.charset) as CharsetPresetId,
    charset: profile.charset,
    token_pattern: profile.token_pattern ?? '',
    pattern_strict: profile.pattern_strict,
    alignment: profile.alignment,
    spacing_mode: profile.spacing_mode,
    ready_threshold: String(profile.ready_threshold),
    use_auto_glyphs: profile.use_auto_glyphs,
  });
  const set = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const save = useMutation({
    mutationFn: (body: ProfileUpdate) => updateProfile(profile.id, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.profile(profile.id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.profiles });
      toast({ message: 'Profile settings saved', tone: 'success' });
    },
  });
  const server = fieldErrors(save.error);
  const conflict = errorCode(save.error) === 'CONFLICT';
  const readOnly = Boolean(profile.archived_at);

  const charset =
    draft.preset === 'custom'
      ? draft.charset
      : (CHARSET_PRESETS.find((p) => p.id === draft.preset)?.charset ?? draft.charset);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate({
      name: draft.name.trim(),
      description: draft.description.trim() || null,
      surface_type: draft.surface_type,
      charset,
      token_pattern: draft.token_pattern.trim() || null,
      pattern_strict: Boolean(draft.token_pattern.trim()) && draft.pattern_strict,
      alignment: draft.alignment,
      spacing_mode: draft.spacing_mode,
      ready_threshold: Number(draft.ready_threshold),
      use_auto_glyphs: draft.use_auto_glyphs,
    });
  };

  return (
    <form className={styles.form} onSubmit={submit} noValidate aria-label="Profile settings">
      <fieldset disabled={readOnly} className={styles.fieldset}>
        <TextField
          label="Name"
          value={draft.name}
          onChange={(e) => set('name', e.target.value)}
          maxLength={60}
          error={conflict ? 'A profile with this name already exists' : server['name']}
        />
        <TextField
          label="Description"
          value={draft.description}
          onChange={(e) => set('description', e.target.value)}
          maxLength={500}
        />
        <SurfaceTypePicker value={draft.surface_type} onChange={(v) => set('surface_type', v)} />
        <Select
          label="Character set"
          value={draft.preset}
          onChange={(e) => set('preset', e.target.value as CharsetPresetId)}
          options={CHARSET_PRESETS.map((p) => ({ value: p.id, label: p.label }))}
        />
        {draft.preset === 'custom' ? (
          <TextField
            label="Characters"
            value={draft.charset}
            onChange={(e) => set('charset', e.target.value)}
            maxLength={96}
            error={server['charset']}
            className={styles.mono}
            helper="Glyphs whose character you remove are kept but no longer used."
          />
        ) : null}
        <TextField
          label="Token pattern"
          value={draft.token_pattern}
          onChange={(e) => set('token_pattern', e.target.value)}
          error={server['token_pattern']}
          className={styles.mono}
          helper="Optional regular expression new tokens should match."
        />
        <Checkbox
          label="Reject tokens that do not match the pattern"
          checked={draft.pattern_strict}
          disabled={!draft.token_pattern.trim()}
          onChange={(e) => set('pattern_strict', e.target.checked)}
        />
        <div className={styles.formRow}>
          <Select
            label="Alignment"
            value={draft.alignment}
            onChange={(e) => set('alignment', e.target.value as Profile['alignment'])}
            options={ALIGNMENTS}
          />
          <Select
            label="Spacing"
            value={draft.spacing_mode}
            onChange={(e) => set('spacing_mode', e.target.value as Profile['spacing_mode'])}
            options={SPACING}
          />
        </div>
        <div className={styles.formRow}>
          <TextField
            label="Glyphs needed per character"
            type="number"
            min={1}
            max={20}
            value={draft.ready_threshold}
            onChange={(e) => set('ready_threshold', e.target.value)}
            error={server['ready_threshold']}
          />
        </div>
        <Toggle
          label="Also use high-quality glyphs that are not reviewed yet"
          checked={draft.use_auto_glyphs}
          onChange={(e) => set('use_auto_glyphs', e.target.checked)}
        />
        {save.error instanceof ApiError && ![409, 422].includes(save.error.status) ? (
          <Banner tone="danger" title="Settings could not be saved." code={save.error.code}>
            {save.error.message}
          </Banner>
        ) : null}
        <div className={styles.formActions}>
          <Button variant="primary" type="submit" loading={save.isPending}>
            Save settings
          </Button>
        </div>
      </fieldset>
    </form>
  );
}

function DangerZone({ profile }: { profile: Profile }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState('');

  const archive = useMutation({
    mutationFn: (archived: boolean) => setProfileArchived(profile.id, archived),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.profile(profile.id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.profiles });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteProfile(profile.id, typed),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.profiles });
      toast({ message: `Profile “${profile.name}” deleted`, tone: 'success' });
      navigate('/profiles');
    },
  });
  const archived = Boolean(profile.archived_at);
  const total = profile.stats.glyphs_auto + profile.stats.glyphs_confirmed;

  return (
    <section className={styles.danger} aria-labelledby="danger-zone">
      <h3 id="danger-zone" className={styles.sectionTitle}>
        Archive and delete
      </h3>
      <div className={styles.dangerRow}>
        <p className={styles.muted}>
          {archived
            ? 'Restore the profile to use and edit it again.'
            : 'Archiving hides the profile and makes it read-only. Nothing is deleted.'}
        </p>
        <Button loading={archive.isPending} onClick={() => archive.mutate(!archived)}>
          {archived ? 'Restore profile' : 'Archive profile'}
        </Button>
      </div>
      {archived ? (
        <div className={styles.dangerRow}>
          <p className={styles.muted}>Permanent delete removes all references and glyphs.</p>
          <Button variant="danger" onClick={() => setConfirming(true)}>
            Delete permanently…
          </Button>
        </div>
      ) : null}
      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        size="sm"
        title="Delete profile permanently?"
        footer={
          <>
            <Button onClick={() => setConfirming(false)}>Cancel</Button>
            <Button
              variant="danger"
              disabled={typed !== profile.name}
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Delete profile
            </Button>
          </>
        }
      >
        <div className={styles.form}>
          <p>
            Permanently delete <strong>{profile.name}</strong>? {total} glyphs and{' '}
            {profile.stats.references} reference images will be deleted. This cannot be undone.
          </p>
          <TextField
            label="Type the profile name to confirm"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            error={remove.error instanceof ApiError ? remove.error.message : undefined}
          />
        </div>
      </Dialog>
    </section>
  );
}

export function SettingsTab({ profile }: { profile: Profile }) {
  return (
    <div className={styles.section}>
      {/* Remount the form when the server copy changes (e.g. after restore). */}
      <SettingsForm key={`${profile.updated_at}-${profile.archived_at}`} profile={profile} />
      <DangerZone profile={profile} />
    </div>
  );
}
