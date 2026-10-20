import { CircleAlert, CircleCheck, CircleX } from 'lucide-react';
import type { ReactNode } from 'react';

import styles from './MetricRow.module.css';

export type MetricStatus = 'pass' | 'warn' | 'fail';

export interface MetricRowProps {
  label: string;
  value: ReactNode;
  unit?: string;
  status?: MetricStatus;
}

const STATUS = {
  pass: { icon: CircleCheck, text: 'Pass' },
  warn: { icon: CircleAlert, text: 'Warning' },
  fail: { icon: CircleX, text: 'Fail' },
} as const;

/** label · value (mono) · unit · status icon (DESIGN.md §6.3). */
export function MetricRow({ label, value, unit, status }: MetricRowProps) {
  const statusInfo = status ? STATUS[status] : null;
  const Icon = statusInfo?.icon;
  return (
    <div className={styles.row}>
      <dt className={styles.label}>{label}</dt>
      <dd className={styles.value}>
        <span className={styles.number}>{value}</span>
        {unit ? <span className={styles.unit}>{unit}</span> : null}
        {Icon && status ? (
          <span className={[styles.status, styles[status]].join(' ')}>
            <Icon aria-hidden />
            <span className="visually-hidden">{statusInfo.text}</span>
          </span>
        ) : null}
      </dd>
    </div>
  );
}

/** Wrap MetricRows so they form a valid description list. */
export function MetricList({ children }: { children: ReactNode }) {
  return <dl className={styles.list}>{children}</dl>;
}
