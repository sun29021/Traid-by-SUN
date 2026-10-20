import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Banner, DropZone, IMAGE_TYPES, Select, useToast } from '@/components';
import { ApiError } from '@/lib/api/client';
import { createJob } from '@/lib/api/jobs';
import { listProfiles } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { Profile } from '@/lib/api/types';

import styles from './Editor.module.css';

const LAST_PROFILE_KEY = 'traid.lastProfileId';

function readLastProfile(): string | null {
  try {
    return window.localStorage.getItem(LAST_PROFILE_KEY);
  } catch {
    return null;
  }
}

function rememberProfile(profileId: string) {
  try {
    window.localStorage.setItem(LAST_PROFILE_KEY, profileId);
  } catch {
    // Private mode or blocked storage: the default is just less convenient.
  }
}

const STATUS_LABEL: Record<Profile['status'], string> = {
  ready: 'Ready',
  training: 'Training',
  needs_review: 'Needs review',
  draft: 'Not ready',
};

/** Profile picker + drop zone that starts an edit job and opens it in the Editor. */
export function NewJob({ size = 'lg' }: { size?: 'md' | 'lg' }) {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const profiles = useQuery({
    queryKey: queryKeys.profileList('false'),
    queryFn: ({ signal }) => listProfiles({ archived: 'false' }, signal),
  });
  const [chosen, setProfileId] = useState<string>('');
  const list = profiles.data ?? [];
  const last = readLastProfile();
  const profileId = list.some((p) => p.id === chosen)
    ? chosen
    : ((list.find((p) => p.id === last) ?? list.find((p) => p.status === 'ready') ?? list[0])?.id ??
      '');

  const start = useMutation({
    mutationFn: (file: File) => createJob(profileId, file),
    onSuccess: (created) => {
      rememberProfile(profileId);
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      navigate(`/editor/${created.job.id}`);
    },
    onError: (error) => {
      toast({
        tone: 'danger',
        message: `Could not open the image. ${error instanceof ApiError ? error.message : 'Please try again.'}`,
      });
    },
  });

  if (profiles.isSuccess && profiles.data.length === 0) {
    return (
      <div className={styles.guide}>
        <h2 className={styles.guideTitle}>Three steps to your first edit</h2>
        <ol className={styles.guideSteps}>
          <li>
            <Link to="/profiles">Create a Style Profile</Link> for the kind of text you edit.
          </li>
          <li>Upload a few reference photos of that text and review the glyphs.</li>
          <li>Drop a target image here.</li>
        </ol>
      </div>
    );
  }

  const selected = profiles.data?.find((p) => p.id === profileId);
  return (
    <div className={styles.newJob}>
      <Select
        label="Style Profile"
        value={profileId}
        onChange={(event) => setProfileId(event.target.value)}
        options={(profiles.data ?? []).map((p) => ({
          value: p.id,
          label: `${p.name} · ${STATUS_LABEL[p.status]}`,
        }))}
        helper={
          selected && selected.status !== 'ready'
            ? 'This profile is not ready yet: characters without reviewed glyphs cannot be rendered.'
            : undefined
        }
      />
      <DropZone
        title={start.isPending ? 'Uploading…' : 'Drop a target image'}
        hint="JPEG, PNG or TIFF. Or browse files."
        accept={IMAGE_TYPES}
        size={size}
        disabled={!profileId || start.isPending}
        onFiles={(files) => {
          const [file] = files;
          if (file) start.mutate(file);
        }}
        onReject={() => toast({ tone: 'danger', message: 'Not supported: use JPEG, PNG or TIFF.' })}
      />
      {profiles.isError && (
        <Banner tone="danger" title="Profiles could not be loaded.">
          Check that the engine is running.
        </Banner>
      )}
    </div>
  );
}
