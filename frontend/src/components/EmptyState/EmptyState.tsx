import type { ReactNode } from 'react';

import styles from './EmptyState.module.css';

export interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  /** At most one primary action (DESIGN.md §9.1). */
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <section className={styles.root} aria-label={title}>
      <span className={styles.icon} aria-hidden>
        {icon}
      </span>
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.description}>{description}</p>
      {action ? <div className={styles.action}>{action}</div> : null}
    </section>
  );
}
