import {
  Columns2,
  Eye,
  EyeOff,
  Maximize,
  ScanLine,
  SquareDashed,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import {
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type WheelEvent,
} from 'react';

import { IconButton } from '@/components';
import type { DetectedRegion, Quad } from '@/lib/api/types';

import styles from './Editor.module.css';
import type { EditorAction, EditorState } from './editorStore';

const MIN_ZOOM = 0.05;
const MAX_ZOOM = 16;
const ZOOM_STEP = 1.25;
const HANDLE_PX = 5;

export interface EditorCanvasProps {
  inputUrl: string;
  resultUrl: string | null;
  maskUrl: string | null;
  width: number;
  height: number;
  regions: readonly DetectedRegion[];
  selectedRegionId: string | null;
  selectedQuad: Quad | null;
  editable: boolean;
  state: EditorState;
  dispatch: (action: EditorAction) => void;
  onSelectRegion: (regionId: string) => void;
  onQuadChange: (quad: Quad) => void;
  device?: string | undefined;
}

interface View {
  scale: number;
  x: number;
  y: number;
}

const toPoints = (quad: Quad) => quad.map(([x, y]) => `${x},${y}`).join(' ');

export function EditorCanvas({
  inputUrl,
  resultUrl,
  maskUrl,
  width,
  height,
  regions,
  selectedRegionId,
  selectedQuad,
  editable,
  state,
  dispatch,
  onSelectRegion,
  onQuadChange,
  device,
}: EditorCanvasProps) {
  const frame = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  // A dragged/nudged quad, valid only while the server's quad is the one it started from.
  const [edit, setEdit] = useState<{ base: Quad | null; quad: Quad } | null>(null);
  const draft = edit && edit.base === selectedQuad ? edit.quad : null;
  const setDraft = (quad: Quad | null) => setEdit(quad ? { base: selectedQuad, quad } : null);
  const [activeHandle, setActiveHandle] = useState<number | null>(null);
  const drag = useRef<
    | { kind: 'pan'; startX: number; startY: number; view: View }
    | { kind: 'handle'; index: number }
    | { kind: 'split' }
    | null
  >(null);

  const quad = draft ?? selectedQuad;

  const fit = useCallback(() => {
    const box = frame.current?.getBoundingClientRect();
    if (!box || !width || !height) return;
    const scale = Math.min(box.width / width, box.height / height) * 0.95;
    setView({
      scale,
      x: (box.width - width * scale) / 2,
      y: (box.height - height * scale) / 2,
    });
  }, [width, height]);

  useLayoutEffect(() => {
    fit();
  }, [fit, inputUrl]);

  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    setView((current) => {
      const box = frame.current?.getBoundingClientRect();
      const px = cx ?? (box ? box.width / 2 : 0);
      const py = cy ?? (box ? box.height / 2 : 0);
      const scale = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.scale * factor));
      const ratio = scale / current.scale;
      return { scale, x: px - (px - current.x) * ratio, y: py - (py - current.y) * ratio };
    });
  }, []);

  const zoomTo = useCallback((scale: number) => zoomAt(scale / view.scale), [zoomAt, view.scale]);

  const toImage = (clientX: number, clientY: number): [number, number] => {
    const box = frame.current?.getBoundingClientRect();
    const left = box?.left ?? 0;
    const top = box?.top ?? 0;
    return [(clientX - left - view.x) / view.scale, (clientY - top - view.y) / view.scale];
  };

  const onWheel = (event: WheelEvent) => {
    const box = frame.current?.getBoundingClientRect();
    if (event.ctrlKey || event.metaKey) {
      zoomAt(
        event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP,
        event.clientX - (box?.left ?? 0),
        event.clientY - (box?.top ?? 0),
      );
    } else {
      setView((v) => ({ ...v, x: v.x - event.deltaX, y: v.y - event.deltaY }));
    }
  };

  const onPointerDown = (event: PointerEvent) => {
    const target = event.target as Element;
    const handle = target.getAttribute('data-handle');
    if (handle !== null && editable) {
      drag.current = { kind: 'handle', index: Number(handle) };
      setActiveHandle(Number(handle));
    } else if (target.getAttribute('data-split') !== null) {
      drag.current = { kind: 'split' };
    } else if (target.getAttribute('data-region') !== null && event.button === 0) {
      onSelectRegion(String(target.getAttribute('data-region')));
      return;
    } else {
      drag.current = { kind: 'pan', startX: event.clientX, startY: event.clientY, view };
    }
    frame.current?.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent) => {
    const [ix, iy] = toImage(event.clientX, event.clientY);
    setCursor(ix >= 0 && iy >= 0 && ix < width && iy < height ? [ix, iy] : null);
    const current = drag.current;
    if (!current) return;
    if (current.kind === 'pan') {
      setView({
        ...current.view,
        x: current.view.x + event.clientX - current.startX,
        y: current.view.y + event.clientY - current.startY,
      });
    } else if (current.kind === 'handle' && quad) {
      const next = quad.map((point, i) =>
        i === current.index
          ? [
              Math.round(Math.min(width, Math.max(0, ix))),
              Math.round(Math.min(height, Math.max(0, iy))),
            ]
          : point,
      );
      setDraft(next);
    } else if (current.kind === 'split') {
      dispatch({ type: 'split', value: ix / width });
    }
  };

  const onPointerUp = (event: PointerEvent) => {
    const current = drag.current;
    drag.current = null;
    frame.current?.releasePointerCapture?.(event.pointerId);
    if (current?.kind === 'handle' && draft) onQuadChange(draft);
  };

  const nudge = (dx: number, dy: number) => {
    if (activeHandle === null || !quad || !editable) {
      setView((v) => ({ ...v, x: v.x - dx * 20, y: v.y - dy * 20 }));
      return;
    }
    const next = quad.map(([px = 0, py = 0], i) =>
      i === activeHandle ? [px + dx, py + dy] : [px, py],
    );
    setDraft(next);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const step = event.shiftKey ? 10 : 1;
    const arrows: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const move = arrows[event.key];
    if (move) {
      event.preventDefault();
      nudge(...move);
    } else if (['1', '2', '3', '4'].includes(event.key) && !event.ctrlKey && editable && quad) {
      setActiveHandle(Number(event.key) - 1);
    } else if (event.key === 'Enter' && draft) {
      onQuadChange(draft);
    } else if (event.key === 'Escape') {
      setActiveHandle(null);
      setDraft(null);
    } else if (event.key === '0' && !event.ctrlKey) {
      fit();
    } else if ((event.key === '=' || event.key === '+') && event.ctrlKey) {
      event.preventDefault();
      zoomAt(ZOOM_STEP);
    } else if (event.key === '-' && event.ctrlKey) {
      event.preventDefault();
      zoomAt(1 / ZOOM_STEP);
    }
  };

  // Commit keyboard nudges after a short pause so every press does not re-render.
  useEffect(() => {
    if (!draft || drag.current) return undefined;
    const timer = window.setTimeout(() => onQuadChange(draft), 600);
    return () => window.clearTimeout(timer);
  }, [draft, onQuadChange]);

  const after = resultUrl ?? inputUrl;
  const showAfter = state.view !== 'before';
  const handleRadius = HANDLE_PX / view.scale;
  const transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  const pixelated = view.scale >= 2 ? styles.pixelated : '';

  return (
    <section className={styles.canvasColumn} aria-label="Image">
      <div className={styles.toolbar} role="toolbar" aria-label="View">
        <IconButton
          label="Zoom out"
          shortcut="Ctrl+-"
          icon={<ZoomOut />}
          onClick={() => zoomAt(1 / ZOOM_STEP)}
        />
        <IconButton
          label="Zoom in"
          shortcut="Ctrl+="
          icon={<ZoomIn />}
          onClick={() => zoomAt(ZOOM_STEP)}
        />
        <IconButton label="Fit to screen" shortcut="0" icon={<Maximize />} onClick={fit} />
        <button type="button" className={styles.zoomButton} onClick={() => zoomTo(1)}>
          100%
        </button>
        <span className={styles.toolbarDivider} aria-hidden />
        <IconButton
          label={state.view === 'before' ? 'Show result' : 'Show original'}
          shortcut="\"
          icon={state.view === 'before' ? <EyeOff /> : <Eye />}
          pressed={state.view === 'before'}
          disabled={!resultUrl}
          onClick={() => dispatch({ type: 'toggleView' })}
        />
        <IconButton
          label="Split view"
          shortcut="S"
          icon={<Columns2 />}
          pressed={state.view === 'split'}
          disabled={!resultUrl}
          onClick={() =>
            dispatch({ type: 'view', view: state.view === 'split' ? 'after' : 'split' })
          }
        />
        <IconButton
          label="Edit mask"
          shortcut="M"
          icon={<ScanLine />}
          pressed={state.showMask}
          disabled={!maskUrl}
          onClick={() => dispatch({ type: 'toggleMask' })}
        />
        <IconButton
          label="Text regions"
          shortcut="G"
          icon={<SquareDashed />}
          pressed={state.showRegions}
          onClick={() => dispatch({ type: 'toggleRegions' })}
        />
        <span className={styles.viewLabel} aria-live="polite">
          {resultUrl
            ? state.view === 'before'
              ? 'Original'
              : state.view === 'split'
                ? 'Split: original | result'
                : 'Result'
            : 'Original'}
        </span>
      </div>

      <div
        ref={frame}
        className={styles.canvas}
        tabIndex={0}
        role="application"
        aria-label="Image canvas. Arrow keys pan or move the selected corner, 1 to 4 select a corner, 0 fits."
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => setCursor(null)}
        onKeyDown={onKeyDown}
      >
        <div className={styles.stage} style={{ width, height, transform }}>
          <img
            className={`${styles.layer} ${pixelated}`}
            src={inputUrl}
            alt="Original image"
            draggable={false}
          />
          {showAfter && resultUrl && (
            <img
              key={resultUrl}
              className={`${styles.layer} ${styles.result} ${pixelated}`}
              src={after}
              alt="Edited result"
              draggable={false}
              style={
                state.view === 'split'
                  ? { clipPath: `inset(0 0 0 ${state.split * 100}%)` }
                  : undefined
              }
            />
          )}
          {state.showMask && maskUrl && (
            <div
              className={styles.maskLayer}
              style={{ maskImage: `url(${maskUrl})`, WebkitMaskImage: `url(${maskUrl})` }}
              aria-hidden
            />
          )}
          <svg
            className={styles.overlay}
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
          >
            {state.showRegions &&
              regions
                .filter((r) => r.id !== selectedRegionId)
                .map((region) => (
                  <polygon
                    key={region.id}
                    data-region={region.id}
                    className={styles.detected}
                    points={toPoints(region.quad)}
                    vectorEffect="non-scaling-stroke"
                  >
                    <title>{`${region.text} (${Math.round(region.confidence * 100)}%)`}</title>
                  </polygon>
                ))}
            {quad && (
              <>
                <polygon
                  className={styles.selectedOutline}
                  points={toPoints(quad)}
                  vectorEffect="non-scaling-stroke"
                />
                <polygon
                  className={styles.selected}
                  points={toPoints(quad)}
                  vectorEffect="non-scaling-stroke"
                />
                {editable &&
                  quad.map(([x, y], index) => (
                    <circle
                      key={index}
                      data-handle={index}
                      className={index === activeHandle ? styles.handleActive : styles.handle}
                      cx={x}
                      cy={y}
                      r={handleRadius}
                      vectorEffect="non-scaling-stroke"
                    >
                      <title>{`Corner ${index + 1}`}</title>
                    </circle>
                  ))}
              </>
            )}
            {state.view === 'split' && resultUrl && (
              <line
                data-split=""
                className={styles.splitLine}
                x1={state.split * width}
                x2={state.split * width}
                y1={0}
                y2={height}
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>
        </div>
      </div>

      <div className={styles.statusBar}>
        <span>{Math.round(view.scale * 100)}%</span>
        <span>{cursor ? `x ${Math.floor(cursor[0])}  y ${Math.floor(cursor[1])}` : '—'}</span>
        <span>
          {width} × {height} px
        </span>
        {device && <span>{device}</span>}
      </div>
    </section>
  );
}
