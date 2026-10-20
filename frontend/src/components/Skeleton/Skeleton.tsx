import styles from './Skeleton.module.css';

export interface SkeletonProps {
  /** `line` = one text line; `block` = thumbnail/canvas area. */
  variant?: 'line' | 'block';
  /** Layout geometry only, e.g. "60%" or 120 (px). */
  width?: string | number;
  height?: string | number;
}

/** Placeholder shown after 300 ms of loading (DESIGN.md §9.1). Hidden from assistive tech. */
export function Skeleton({ variant = 'line', width, height }: SkeletonProps) {
  return (
    <span
      className={[styles.skeleton, styles[variant]].join(' ')}
      style={{ width, height }}
      aria-hidden
    />
  );
}
