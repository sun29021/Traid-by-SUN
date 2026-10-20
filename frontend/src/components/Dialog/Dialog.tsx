import { X } from 'lucide-react';
import { type ReactNode, useEffect, useId, useRef } from 'react';

import { IconButton } from '../IconButton/IconButton';
import styles from './Dialog.module.css';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Actions, right-aligned; put the primary button last (DESIGN.md §6.4). */
  footer?: ReactNode;
  /** `sm` 480 px (confirmations), `md` 640 px (forms). */
  size?: 'sm' | 'md';
  /** `right` renders a 420 px side drawer. */
  placement?: 'center' | 'right';
}

/**
 * Modal built on the native <dialog>: the browser makes the rest of the page inert,
 * traps focus and closes on Esc. Focus returns to the element that opened it.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  placement = 'center',
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      returnFocus.current = document.activeElement as HTMLElement | null;
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
      returnFocus.current?.focus();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      className={[styles.dialog, styles[size], styles[placement]].join(' ')}
      onCancel={(event) => {
        event.preventDefault(); // parent owns `open`
        onClose();
      }}
    >
      <header className={styles.header}>
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <IconButton
          label="Close"
          icon={<X />}
          size="sm"
          onClick={onClose}
          tooltipPlacement="bottom"
        />
      </header>
      <div className={styles.body}>{children}</div>
      {footer ? <footer className={styles.footer}>{footer}</footer> : null}
    </dialog>
  );
}

export function Drawer(props: Omit<DialogProps, 'placement' | 'size'>) {
  return <Dialog {...props} placement="right" />;
}
