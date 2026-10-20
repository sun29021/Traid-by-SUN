import styles from './ProgressBar.module.css';

export interface ProgressBarProps {
  /** 0–1. Omit for an indeterminate bar. */
  value?: number | undefined;
  /** Current step, e.g. "Removing old text" (DESIGN.md §9.1). */
  label: string;
}

export function ProgressBar({ value, label }: ProgressBarProps) {
  const determinate = typeof value === 'number';
  const percent = determinate ? Math.round(Math.min(1, Math.max(0, value)) * 100) : undefined;
  return (
    <div className={styles.root}>
      <div className={styles.labelRow}>
        <span>{label}</span>
        {determinate ? <span className={styles.percent}>{percent}%</span> : null}
      </div>
      <div
        className={styles.track}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div
          className={[styles.fill, determinate ? '' : styles.indeterminate].join(' ')}
          style={determinate ? { width: `${percent}%` } : undefined}
        />
      </div>
    </div>
  );
}
