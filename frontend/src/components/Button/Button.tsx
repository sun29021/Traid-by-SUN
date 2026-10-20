import { Loader2 } from 'lucide-react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Leading icon; replaced by a spinner while loading. */
  icon?: ReactNode;
  loading?: boolean;
}

/** DESIGN.md §6.1 — at most one `primary` per view region. */
export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  loading = false,
  disabled,
  className,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [styles.button, styles[variant], styles[size], className]
    .filter(Boolean)
    .join(' ');
  return (
    <button
      type={type}
      className={classes}
      disabled={disabled === true || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 className={styles.spinner} aria-hidden /> : icon}
      {children}
    </button>
  );
}
