import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { Tooltip } from '../Tooltip/Tooltip';
import styles from './IconButton.module.css';

export interface IconButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-label' | 'children'
> {
  /** Required: used as aria-label and tooltip (DESIGN.md §6.1, §13). */
  label: string;
  icon: ReactNode;
  shortcut?: string;
  size?: 'sm' | 'md';
  /** Toggle buttons (e.g. mask overlay) expose their state. */
  pressed?: boolean;
  tooltipPlacement?: 'top' | 'bottom' | 'right';
}

export function IconButton({
  label,
  icon,
  shortcut,
  size = 'md',
  pressed,
  tooltipPlacement,
  className,
  type = 'button',
  ...rest
}: IconButtonProps) {
  return (
    <Tooltip content={label} shortcut={shortcut} placement={tooltipPlacement}>
      <button
        type={type}
        aria-label={label}
        aria-pressed={pressed}
        className={[styles.button, styles[size], className].filter(Boolean).join(' ')}
        {...rest}
      >
        {icon}
      </button>
    </Tooltip>
  );
}
