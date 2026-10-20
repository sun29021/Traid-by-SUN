import styles from './Badge.module.css';

export type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

export interface BadgeProps {
  tone?: Tone;
  label: string;
}

/** Status = dot + text, never colour alone (DESIGN.md §3.3, §6.3). */
export function Badge({ tone = 'neutral', label }: BadgeProps) {
  return (
    <span className={[styles.badge, styles[tone]].join(' ')}>
      <span className={styles.dot} aria-hidden />
      {label}
    </span>
  );
}
