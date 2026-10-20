import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ImageOff, Images } from 'lucide-react';
import { useState } from 'react';

import {
  Badge,
  Banner,
  Button,
  Dialog,
  Drawer,
  DropZone,
  EmptyState,
  MetricList,
  MetricRow,
  ProgressBar,
  Skeleton,
  TextField,
  useToast,
} from '@/components';
import { ApiError } from '@/lib/api/client';
import {
  deleteReference,
  listReferences,
  reextractReference,
  setKnownText,
  uploadReferences,
} from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { Profile, Reference } from '@/lib/api/types';
import { useTask } from '@/lib/hooks/useTask';

import { REFERENCE_ERRORS, REFERENCE_STATUS } from './profileMeta';
import styles from './References.module.css';

const REFERENCE_PAGE = 100;

function useRefreshKeys(profileId: string) {
  return [
    queryKeys.references(profileId),
    queryKeys.profile(profileId),
    queryKeys.coverage(profileId),
    queryKeys.allGlyphs(profileId),
  ];
}

function ReferenceDrawer({
  profile,
  reference,
  onClose,
  onTask,
}: {
  profile: Profile;
  reference: Reference;
  onClose: () => void;
  onTask: (taskId: string) => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const refresh = useRefreshKeys(profile.id);
  const [knownText, setKnown] = useState(reference.known_text ?? '');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const readOnly = Boolean(profile.archived_at);

  const invalidate = () => {
    for (const key of refresh) void queryClient.invalidateQueries({ queryKey: key });
  };
  const saveText = useMutation({
    mutationFn: () => setKnownText(reference.id, knownText.trim() || null),
    onSuccess: (change) => {
      invalidate();
      if (change.task) onTask(change.task.id);
      toast({
        message: change.task ? 'Known text saved — extracting again' : 'Known text saved',
        tone: 'success',
      });
    },
  });
  const reextract = useMutation({
    mutationFn: () => reextractReference(reference.id),
    onSuccess: (task) => {
      invalidate();
      onTask(task.id);
      onClose();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteReference(reference.id),
    onSuccess: () => {
      invalidate();
      toast({ message: 'Reference image deleted', tone: 'success' });
      onClose();
    },
  });

  const status = REFERENCE_STATUS[reference.status];
  const conditions = reference.conditions;
  return (
    <Drawer open onClose={onClose} title={reference.file.original_name ?? 'Reference image'}>
      <div className={styles.drawer}>
        <img
          src={reference.file.url}
          alt={`Reference image ${reference.file.original_name ?? ''}`}
          className={styles.preview}
        />
        <Badge tone={status.tone} label={status.label} />
        {reference.error_code ? (
          <Banner
            tone="danger"
            title={REFERENCE_ERRORS[reference.error_code] ?? 'Failed'}
            code={reference.error_code}
          />
        ) : null}
        <MetricList>
          <MetricRow label="Glyphs extracted" value={reference.glyph_count} />
          <MetricRow
            label="Size"
            value={`${reference.file.width ?? '?'} × ${reference.file.height ?? '?'}`}
            unit="px"
          />
          {conditions ? (
            <>
              <MetricRow
                label="Text height"
                value={conditions['cap_height_px']?.toFixed(0)}
                unit="px"
              />
              <MetricRow label="Blur" value={conditions['blur_sigma']?.toFixed(2)} unit="σ" />
              <MetricRow label="Grain" value={conditions['noise_sigma']?.toFixed(2)} unit="σ" />
              <MetricRow label="Contrast" value={conditions['contrast']?.toFixed(2)} />
              <MetricRow label="Angle" value={conditions['angle_deg']?.toFixed(1)} unit="°" />
            </>
          ) : null}
        </MetricList>
        <form
          className={styles.knownText}
          onSubmit={(e) => {
            e.preventDefault();
            saveText.mutate();
          }}
        >
          <TextField
            label="Known text (optional)"
            value={knownText}
            onChange={(e) => setKnown(e.target.value)}
            maxLength={64}
            disabled={readOnly}
            className={styles.mono}
            helper="If you type the exact text in this image, characters are labelled from it instead of OCR, and spaces are known."
          />
          <Button type="submit" loading={saveText.isPending} disabled={readOnly}>
            Save known text
          </Button>
        </form>
        <div className={styles.drawerActions}>
          <Button
            onClick={() => reextract.mutate()}
            loading={reextract.isPending}
            disabled={readOnly}
          >
            Extract again
          </Button>
          <Button variant="danger" onClick={() => setConfirmDelete(true)}>
            Delete image
          </Button>
        </div>
      </div>
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        size="sm"
        title="Delete this reference image?"
        footer={
          <>
            <Button onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              Delete image
            </Button>
          </>
        }
      >
        Its {reference.glyph_count} glyphs will be removed from the profile, including reviewed
        ones.
      </Dialog>
    </Drawer>
  );
}

export function ReferencesTab({ profile }: { profile: Profile }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const refresh = useRefreshKeys(profile.id);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const { task, isPending: extracting } = useTask(taskId, refresh);
  const readOnly = Boolean(profile.archived_at);

  const references = useQuery({
    queryKey: queryKeys.references(profile.id),
    queryFn: ({ signal }) => listReferences(profile.id, { limit: REFERENCE_PAGE }, signal),
    refetchInterval: extracting ? 1500 : false,
  });

  const upload = useMutation({
    mutationFn: (files: File[]) => uploadReferences(profile.id, files),
    onSuccess: (result) => {
      for (const key of refresh) void queryClient.invalidateQueries({ queryKey: key });
      if (result.task) setTaskId(result.task.id);
      const parts = [`${result.created.length} added`];
      if (result.skipped.length) parts.push(`${result.skipped.length} already uploaded`);
      if (result.rejected.length) parts.push(`${result.rejected.length} not usable`);
      toast({
        message: parts.join(', '),
        tone: result.rejected.length ? 'danger' : 'success',
      });
    },
  });

  const items = references.data?.items ?? [];
  const open = items.find((r) => r.id === openId) ?? null;

  return (
    <div className={styles.tab}>
      {!readOnly ? (
        <DropZone
          title="Drop reference images"
          hint="Real photos or scans of this text: different angles, lighting and textures. JPEG, PNG or TIFF, up to 50 at a time."
          multiple
          disabled={upload.isPending}
          onFiles={(files) => upload.mutate(files)}
          onReject={(files) =>
            toast({
              message: `${files.length} file${files.length === 1 ? ' is' : 's are'} not JPEG, PNG or TIFF`,
              tone: 'danger',
            })
          }
        />
      ) : null}

      {upload.isPending ? <ProgressBar label="Uploading images…" /> : null}
      {extracting ? (
        <ProgressBar
          label={task?.message ?? 'Waiting for the engine…'}
          value={task?.status === 'running' ? task.progress : undefined}
        />
      ) : null}
      {task?.status === 'failed' ? (
        <Banner tone="danger" title="Glyph extraction stopped." code={task.error_code ?? undefined}>
          {task.message}
        </Banner>
      ) : null}
      {upload.error instanceof ApiError ? (
        <Banner tone="danger" title="Upload failed." code={upload.error.code}>
          {upload.error.message}
        </Banner>
      ) : null}
      {upload.data?.rejected.length ? (
        <Banner tone="warning" title="Some files were not added.">
          <ul className={styles.issues}>
            {upload.data.rejected.map((issue, i) => (
              <li key={`${issue.name}-${i}`}>
                <strong>{issue.name ?? 'File'}</strong>: {issue.message}
              </li>
            ))}
          </ul>
        </Banner>
      ) : null}

      {references.isPending ? (
        <div className={styles.grid} aria-label="Loading reference images">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} variant="block" height={180} />
          ))}
        </div>
      ) : references.isError ? (
        <Banner
          tone="danger"
          title="Reference images could not be loaded."
          action={<Button onClick={() => void references.refetch()}>Retry</Button>}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Images />}
          title="No reference images yet"
          description="Upload real images of this text. Traid cuts every character out as a glyph you can review."
        />
      ) : (
        <ul className={styles.grid} aria-label="Reference images">
          {items.map((reference) => {
            const status = REFERENCE_STATUS[reference.status];
            return (
              <li key={reference.id}>
                <button
                  type="button"
                  className={styles.card}
                  onClick={() => setOpenId(reference.id)}
                >
                  {reference.file.thumb_url ? (
                    <img
                      src={reference.file.thumb_url}
                      alt=""
                      className={styles.thumb}
                      loading="lazy"
                    />
                  ) : (
                    <span className={styles.thumb}>
                      <ImageOff aria-hidden />
                    </span>
                  )}
                  <span className={styles.cardBody}>
                    <span className={styles.cardName}>
                      {reference.file.original_name ?? 'Image'}
                    </span>
                    <span className={styles.cardMeta}>
                      <Badge tone={status.tone} label={status.label} />
                      <span>{reference.glyph_count} glyphs</span>
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {open ? (
        <ReferenceDrawer
          key={open.id}
          profile={profile}
          reference={open}
          onClose={() => setOpenId(null)}
          onTask={setTaskId}
        />
      ) : null}
    </div>
  );
}
