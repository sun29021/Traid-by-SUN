import type { ReactNode } from 'react';

import styles from './Field.module.css';

export interface FieldProps {
  id: string;
  label: string;
  helper?: string | undefined;
  error?: string | undefined;
  /** Optional element on the label row, e.g. a reset button or status chip. */
  labelAside?: ReactNode;
  children: ReactNode;
}

/** Label above, control, helper and error below (DESIGN.md §8). */
export function Field({ id, label, helper, error, labelAside, children }: FieldProps) {
  return (
    <div className={styles.field}>
      <div className={styles.labelRow}>
        <label className={styles.label} htmlFor={id}>
          {label}
        </label>
        {labelAside}
      </div>
      {children}
      {helper ? (
        <p id={`${id}-helper`} className={styles.helper}>
          {helper}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
