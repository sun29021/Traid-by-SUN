import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { useBlocker, useNavigate, useParams } from 'react-router-dom';

import { Badge, Banner, Button, Dialog, IconButton, Skeleton, useToast } from '@/components';
import {
  acceptJob,
  exportJob,
  getJob,
  rejectJob,
  renderJob,
  reopenJob,
  setRegion,
} from '@/lib/api/jobs';
import { getProfile } from '@/lib/api/profiles';
import { queryKeys } from '@/lib/api/queryKeys';
import type { EditJob, JobStatus, Quad, RegionUpdate, RenderParams } from '@/lib/api/types';
import { useTask } from '@/lib/hooks/useTask';

import styles from './Editor.module.css';
import { EditorCanvas } from './EditorCanvas';
import { editorReducer, initialEditorState } from './editorStore';
import { messageFor } from './errors';
import { Inspector, TOKEN_INPUT_ID } from './Inspector';
import { NewJob } from './NewJob';
import { useEditorShortcuts } from './useEditorShortcuts';

const TRANSIENT: ReadonlySet<JobStatus> = new Set(['uploaded', 'detecting', 'rendering']);
const POLL_MS = 600;
const RERENDER_DELAY_MS = 450;

const JOB_ERRORS: Record<string, string> = {
  GLYPH_MISSING: 'Some characters have no usable glyph. Review more glyphs for this profile.',
  SEGMENTATION_FAILED: 'The old token could not be split into characters. Adjust the region.',
  MODEL_UNAVAILABLE: 'The AI models are not installed. Run scripts\\setup.ps1.',
  OUT_OF_MEMORY: 'Not enough memory for this image.',
  INTERNAL_ERROR: 'Something went wrong while rendering. Try again.',
};

export function EditorPage() {
  const { jobId } = useParams();
  if (!jobId) {
    return (
      <div className={styles.emptyEditor}>
        <h2 className={styles.emptyTitle}>Open an image to edit</h2>
        <NewJob />
      </div>
    );
  }
  return <JobEditor key={jobId} jobId={jobId} />;
}

function centredQuad(job: EditJob): Quad {
  const w = job.input.width ?? 100;
  const h = job.input.height ?? 100;
  const [x0, x1, y0, y1] = [w * 0.35, w * 0.65, h * 0.45, h * 0.55].map(Math.round) as [
    number,
    number,
    number,
    number,
  ];
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

function JobEditor({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const jobQuery = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: ({ signal }) => getJob(jobId, signal),
    refetchInterval: (query) =>
      query.state.data && TRANSIENT.has(query.state.data.status) ? POLL_MS : false,
  });
  const job = jobQuery.data;
  const profileQuery = useQuery({
    queryKey: queryKeys.profile(job?.profile_id ?? 'none'),
    queryFn: ({ signal }) => getProfile(job?.profile_id as string, signal),
    enabled: Boolean(job?.profile_id),
  });
  const profile = profileQuery.data;

  const [state, dispatch] = useReducer(editorReducer, undefined, () => initialEditorState());
  const [newText, setNewText] = useState('');
  const [renderTaskId, setRenderTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exported, setExported] = useState<{ url: string; name: string } | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [showRegions, setShowRegions] = useState(true);
  const [showInspector, setShowInspector] = useState(true);
  const { task: renderTask } = useTask(renderTaskId, [queryKeys.job(jobId), queryKeys.jobs]);

  // Start from the job's saved text and adjustments once.
  const loaded = useRef(false);
  useEffect(() => {
    if (!job || loaded.current) return;
    loaded.current = true;
    dispatch({ type: 'load', params: job.params });
    setNewText(job.new_text ?? '');
  }, [job]);

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.job(jobId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
  }, [queryClient, jobId]);

  const render = useMutation({
    mutationFn: ({ text, params }: { text: string; params: RenderParams }) =>
      renderJob(jobId, text, params),
    onSuccess: (task) => {
      setRenderTaskId(task.id);
      setError(null);
      refresh();
    },
    onError: (e) => setError(messageFor(e)),
  });

  const region = useMutation({
    mutationFn: (body: RegionUpdate) => setRegion(jobId, body),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.job(jobId), data);
      setError(null);
    },
    onError: (e) => setError(messageFor(e)),
  });

  const decide = useMutation({
    mutationFn: (action: 'accept' | 'reject') =>
      action === 'accept' ? acceptJob(jobId) : rejectJob(jobId),
    onSuccess: (data, action) => {
      queryClient.setQueryData(queryKeys.job(jobId), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      toast({
        tone: 'success',
        message: action === 'accept' ? 'Result accepted' : 'Result rejected',
      });
    },
    onError: (e) => setError(messageFor(e)),
  });

  const exporter = useMutation({
    mutationFn: () => exportJob(jobId),
    onSuccess: (result) => {
      const url = `${result.file.url}?download=1`;
      setExported({ url, name: result.download_name });
      const link = document.createElement('a');
      link.href = url;
      link.download = result.download_name;
      document.body.append(link);
      link.click();
      link.remove();
      refresh();
    },
    onError: (e) => setError(messageFor(e)),
  });

  const reopen = useMutation({
    mutationFn: () => reopenJob(jobId),
    onSuccess: (copy) => navigate(`/editor/${copy.id}`),
    onError: (e) => setError(messageFor(e)),
  });

  const busy = render.isPending || decide.isPending || exporter.isPending || region.isPending;

  const generate = useCallback(() => {
    if (!job || job.status === 'accepted' || !newText) return;
    render.mutate({ text: newText, params: state.params });
  }, [job, newText, render, state.params]);

  // Adjustments re-render automatically (debounced) once there is a result.
  const savedParams = JSON.stringify(job?.params ?? null);
  useEffect(() => {
    if (!job?.result || job.status === 'accepted' || !job.new_text) return undefined;
    if (JSON.stringify(state.params) === savedParams) return undefined;
    const text = job.new_text;
    const timer = window.setTimeout(
      () => render.mutate({ text, params: state.params }),
      RERENDER_DELAY_MS,
    );
    return () => window.clearTimeout(timer);
    // `render` and `job` change identity every poll; only adjustments should trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.params]);

  const onQuadChange = useCallback(
    (quad: Quad) => {
      if (!job) return;
      region.mutate({ quad, ...(job.original_text ? { original_text: job.original_text } : {}) });
    },
    [job, region],
  );

  useEditorShortcuts({
    dispatch,
    generate,
    accept: () => job?.status === 'rendered' && decide.mutate('accept'),
    reject: () => job?.status === 'rendered' && setRejecting(true),
    exportFile: () => job?.status === 'accepted' && exporter.mutate(),
    focusToken: () => document.getElementById(TOKEN_INPUT_ID)?.focus(),
    toggleRegionsPanel: () => setShowRegions((v) => !v),
    toggleInspector: () => setShowInspector((v) => !v),
  });

  // Leaving with an unreviewed result asks first (DESIGN.md §11.5).
  const unreviewed = job?.status === 'rendered';
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      unreviewed && currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (!unreviewed) return undefined;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [unreviewed]);

  if (jobQuery.isPending) {
    return (
      <div className={styles.emptyEditor}>
        <Skeleton height={320} />
      </div>
    );
  }
  if (jobQuery.isError || !job) {
    return (
      <div className={styles.emptyEditor}>
        <Banner tone="danger" title="This edit job could not be loaded.">
          It may have been deleted.
        </Banner>
      </div>
    );
  }

  const jobError =
    job.status === 'failed' && job.error_code
      ? (JOB_ERRORS[job.error_code] ?? job.error_code)
      : null;

  return (
    <div className={styles.editor} data-regions={showRegions} data-inspector={showInspector}>
      {showRegions && (
        <aside className={styles.regionsPanel} aria-label="Text regions">
          <div className={styles.panelHeader}>
            <h2 className={styles.sectionTitle}>Regions</h2>
            <IconButton
              label="Hide regions"
              shortcut="["
              icon={<PanelLeftClose />}
              size="sm"
              onClick={() => setShowRegions(false)}
            />
          </div>
          {job.regions.length === 0 && (
            <p className={styles.muted}>
              {TRANSIENT.has(job.status) ? 'Finding text…' : 'No text regions detected.'}
            </p>
          )}
          <ul className={styles.regionList}>
            {job.regions.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className={styles.regionRow}
                  aria-pressed={r.id === job.selected_region_id}
                  disabled={job.status === 'accepted' || busy}
                  onClick={() => region.mutate({ region_id: r.id })}
                >
                  <span className={styles.mono}>{r.text || '—'}</span>
                  <span className={styles.regionMeta}>
                    {Math.round(r.confidence * 100)}% read
                    {r.id === job.regions[0]?.id && <Badge tone="info" label="Token" />}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
      )}
      {!showRegions && (
        <IconButton
          className={styles.reopenLeft}
          label="Show regions"
          shortcut="["
          icon={<PanelLeftOpen />}
          size="sm"
          onClick={() => setShowRegions(true)}
        />
      )}

      <EditorCanvas
        inputUrl={job.input.url}
        resultUrl={job.result?.url ?? null}
        maskUrl={job.mask?.url ?? null}
        width={job.input.width ?? 0}
        height={job.input.height ?? 0}
        regions={job.regions}
        selectedRegionId={job.selected_region_id}
        selectedQuad={job.selected_quad}
        editable={job.status !== 'accepted' && !TRANSIENT.has(job.status)}
        state={state}
        dispatch={dispatch}
        onSelectRegion={(regionId) => region.mutate({ region_id: regionId })}
        onQuadChange={onQuadChange}
      />

      {showInspector ? (
        <div className={styles.inspectorColumn}>
          <div className={styles.panelHeader}>
            <span className={styles.jobStatus}>
              <Badge
                tone={
                  job.status === 'accepted'
                    ? 'success'
                    : job.status === 'failed'
                      ? 'danger'
                      : 'neutral'
                }
                label={job.status}
              />
            </span>
            <IconButton
              label="Hide inspector"
              shortcut="]"
              icon={<PanelRightClose />}
              size="sm"
              onClick={() => setShowInspector(false)}
            />
          </div>
          <Inspector
            job={job}
            profile={profile}
            newText={newText}
            onNewText={setNewText}
            state={state}
            dispatch={dispatch}
            renderTask={renderTask}
            busy={busy}
            onGenerate={generate}
            onAccept={() => decide.mutate('accept')}
            onReject={() => setRejecting(true)}
            onExport={() => exporter.mutate()}
            onReopen={() => reopen.mutate()}
            onFixOldText={(text) =>
              region.mutate(
                job.selected_region_id
                  ? { region_id: job.selected_region_id, original_text: text }
                  : { quad: job.selected_quad ?? centredQuad(job), original_text: text },
              )
            }
            onDrawRegion={() => region.mutate({ quad: centredQuad(job) })}
            exported={exported}
            error={error ?? jobError}
          />
        </div>
      ) : (
        <IconButton
          className={styles.reopenRight}
          label="Show inspector"
          shortcut="]"
          icon={<PanelRightOpen />}
          size="sm"
          onClick={() => setShowInspector(true)}
        />
      )}

      <Dialog
        open={rejecting}
        onClose={() => setRejecting(false)}
        title="Reject this result?"
        size="sm"
        footer={
          <>
            <Button onClick={() => setRejecting(false)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() => {
                setRejecting(false);
                decide.mutate('reject');
              }}
            >
              Reject
            </Button>
          </>
        }
      >
        <p>The glyphs used here are ranked lower next time. You can adjust and re-generate.</p>
      </Dialog>

      <Dialog
        open={blocker.state === 'blocked'}
        onClose={() => blocker.reset?.()}
        title="Leave without deciding?"
        size="sm"
        footer={
          <>
            <Button onClick={() => blocker.reset?.()}>Stay</Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              Leave
            </Button>
          </>
        }
      >
        <p>This result is not accepted yet. It stays in History, but nothing is exported.</p>
      </Dialog>
    </div>
  );
}
