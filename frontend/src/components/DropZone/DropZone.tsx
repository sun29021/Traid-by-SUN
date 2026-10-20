import { Upload } from 'lucide-react';
import { type DragEvent, useId, useRef, useState } from 'react';

import { Button } from '../Button/Button';
import styles from './DropZone.module.css';
import { IMAGE_TYPES } from './fileTypes';

export interface DropZoneProps {
  title: string;
  hint?: string;
  /** Allowed MIME types; others are reported through `onReject`. */
  accept?: readonly string[];
  multiple?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
  onReject?: (files: File[]) => void;
  /** Taller zone for primary entry points (Home). */
  size?: 'md' | 'lg';
}

type DragState = 'idle' | 'over' | 'invalid';

/**
 * File drop target with a keyboard-accessible "Browse files" button (DESIGN.md §6.2,
 * §10.3). The server re-validates every file; this only filters obvious mistakes.
 */
export function DropZone({
  title,
  hint,
  accept = IMAGE_TYPES,
  multiple = false,
  disabled = false,
  onFiles,
  onReject,
  size = 'md',
}: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [drag, setDrag] = useState<DragState>('idle');

  const isAccepted = (type: string) => accept.includes(type);

  const deliver = (fileList: FileList | null) => {
    const files = Array.from(fileList ?? []);
    const chosen = multiple ? files : files.slice(0, 1);
    const ok = chosen.filter((file) => isAccepted(file.type));
    const rejected = chosen.filter((file) => !isAccepted(file.type));
    if (ok.length) onFiles(ok);
    if (rejected.length) onReject?.(rejected);
  };

  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) return;
    event.preventDefault();
    const items = Array.from(event.dataTransfer.items);
    const valid = items.length > 0 && items.every((item) => isAccepted(item.type));
    setDrag(valid ? 'over' : 'invalid');
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) return;
    event.preventDefault();
    setDrag('idle');
    deliver(event.dataTransfer.files);
  };

  const label =
    drag === 'over' ? 'Release to upload' : drag === 'invalid' ? 'Not supported' : title;

  return (
    <div
      className={[styles.zone, styles[size], styles[drag], disabled ? styles.disabled : '']
        .filter(Boolean)
        .join(' ')}
      onDragOver={onDragOver}
      onDragLeave={() => setDrag('idle')}
      onDrop={onDrop}
    >
      <Upload className={styles.icon} aria-hidden />
      <p className={styles.title}>{label}</p>
      {hint ? (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      ) : null}
      <Button
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        aria-describedby={hint ? hintId : undefined}
      >
        Browse files
      </Button>
      <input
        ref={inputRef}
        type="file"
        className="visually-hidden"
        tabIndex={-1}
        aria-hidden
        accept={accept.join(',')}
        multiple={multiple}
        onChange={(event) => {
          deliver(event.target.files);
          event.target.value = ''; // allow choosing the same file again
        }}
      />
    </div>
  );
}
