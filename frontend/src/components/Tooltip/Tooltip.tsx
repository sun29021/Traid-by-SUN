import { cloneElement, type ReactElement, useId } from 'react';

import styles from './Tooltip.module.css';

export interface TooltipProps {
  content: string;
  /** Keyboard shortcut shown in mono, e.g. "\\" or "Ctrl+Enter". */
  shortcut?: string | undefined;
  /** A single focusable element (button, link). */
  children: ReactElement<{ 'aria-describedby'?: string }>;
  placement?: 'top' | 'bottom' | 'right' | undefined;
}

/** Shows on hover and keyboard focus after 300 ms (DESIGN.md §6.5). Pure CSS, no portal. */
export function Tooltip({ content, shortcut, children, placement = 'top' }: TooltipProps) {
  const id = useId();
  return (
    <span className={styles.host}>
      {cloneElement(children, { 'aria-describedby': id })}
      <span id={id} role="tooltip" className={[styles.tooltip, styles[placement]].join(' ')}>
        {content}
        {shortcut ? <kbd className={styles.shortcut}>{shortcut}</kbd> : null}
      </span>
    </span>
  );
}
