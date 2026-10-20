import { CircleAlert, Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import styles from './Banner.module.css';

export interface BannerProps {
  tone: 'info' | 'warning' | 'danger';
  title: string;
  children?: ReactNode;
  /** e.g. a Retry button. */
  action?: ReactNode;
  /** Error codes are shown small and mono for debugging (DESIGN.md §9.2). */
  code?: string | undefined;
}

const ICONS = { info: Info, warning: TriangleAlert, danger: CircleAlert } as const;

/** Persistent page/panel message (DESIGN.md §6.4). Danger banners are announced assertively. */
export function Banner({ tone, title, children, action, code }: BannerProps) {
  const Icon = ICONS[tone];
  return (
    <div
      className={[styles.banner, styles[tone]].join(' ')}
      role={tone === 'danger' ? 'alert' : 'status'}
    >
      <Icon className={styles.icon} aria-hidden />
      <div className={styles.body}>
        <p className={styles.title}>{title}</p>
        {children ? <div className={styles.text}>{children}</div> : null}
        {code ? <code className={styles.code}>{code}</code> : null}
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
