import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Banner, Button, Dialog, Select, TextField } from '@/components';
import { ApiError } from '@/lib/api/client';
import { createProfile } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { SurfaceType } from '@/lib/api/types';

import { errorCode, fieldErrors } from './errors';
import { CHARSET_PRESETS, type CharsetPresetId } from './profileMeta';
import styles from './Profiles.module.css';
import { SurfaceTypePicker } from './SurfaceTypePicker';

interface CreateProfileDialogProps {
  open: boolean;
  onClose: () => void;
}

export function CreateProfileDialog({ open, onClose }: CreateProfileDialogProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [surface, setSurface] = useState<SurfaceType | null>(null);
  const [description, setDescription] = useState('');
  const [preset, setPreset] = useState<CharsetPresetId>('upper_digits');
  const [customCharset, setCustomCharset] = useState('');
  const [pattern, setPattern] = useState('');
  const [touched, setTouched] = useState(false);

  const create = useMutation({
    mutationFn: createProfile,
    onSuccess: (profile) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.profiles });
      onClose();
      navigate(`/profiles/${profile.id}/references`);
    },
  });

  const server = fieldErrors(create.error);
  const nameError =
    (touched && !name.trim() ? 'Give the profile a name' : undefined) ??
    (errorCode(create.error) === 'CONFLICT'
      ? 'A profile with this name already exists'
      : undefined) ??
    server['name'];
  const surfaceError =
    touched && !surface ? 'Choose how the text was made' : server['surface_type'];
  const charset =
    preset === 'custom'
      ? customCharset
      : (CHARSET_PRESETS.find((p) => p.id === preset)?.charset ?? '');
  const charsetError =
    (touched && preset === 'custom' && !customCharset
      ? 'Type the characters this text uses'
      : undefined) ?? server['charset'];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (!name.trim() || !surface || !charset) return;
    create.mutate({
      name: name.trim(),
      surface_type: surface,
      description: description.trim() || null,
      charset,
      token_pattern: pattern.trim() || null,
    });
  };

  const unexpected =
    create.error instanceof ApiError && ![409, 422].includes(create.error.status)
      ? create.error
      : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New Style Profile"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" form="create-profile" loading={create.isPending}>
            Create profile
          </Button>
        </>
      }
    >
      <form id="create-profile" onSubmit={submit} noValidate className={styles.form}>
        <TextField
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={60}
          error={nameError}
          helper="Required. One profile per text style, e.g. “Receipt token A”."
          autoFocus
        />
        <SurfaceTypePicker value={surface} onChange={setSurface} error={surfaceError} />
        <Select
          label="Character set"
          value={preset}
          onChange={(e) => setPreset(e.target.value as CharsetPresetId)}
          options={CHARSET_PRESETS.map((p) => ({ value: p.id, label: p.label }))}
          helper="Only these characters can appear in tokens. You can change it later."
        />
        {preset === 'custom' ? (
          <TextField
            label="Custom characters"
            value={customCharset}
            onChange={(e) => setCustomCharset(e.target.value)}
            maxLength={96}
            error={charsetError}
            className={styles.mono}
          />
        ) : null}
        <TextField
          label="Token pattern (optional)"
          value={pattern}
          onChange={(e) => setPattern(e.target.value)}
          placeholder="^[A-Z]\d-\d{6}$"
          error={server['token_pattern']}
          helper="A regular expression new tokens should match."
          className={styles.mono}
        />
        <TextField
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={500}
        />
        {unexpected ? (
          <Banner tone="danger" title="Could not create the profile." code={unexpected.code}>
            {unexpected.message}
          </Banner>
        ) : null}
      </form>
    </Dialog>
  );
}
