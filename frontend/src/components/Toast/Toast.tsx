import { CircleAlert, CircleCheck, Info, X } from 'lucide-react';
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import styles from './Toast.module.css';
import { type ToastInput, ToastContext } from './toastContext';

const AUTO_DISMISS_MS = 5000;
const MAX_VISIBLE = 3;
const ICONS = { info: Info, success: CircleCheck, danger: CircleAlert } as const;

interface ToastItem extends ToastInput {
  id: number;
}

/**
 * Bottom-right toasts (DESIGN.md §6.4): max 3, auto-dismiss after 5 s except errors.
 * Messages are announced through polite/assertive live regions.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback((input: ToastInput) => {
    const id = nextId.current++;
    setItems((current) => [...current, { ...input, id }].slice(-MAX_VISIBLE));
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={styles.region} role="status" aria-live="polite" aria-label="Notifications">
        {items
          .filter((item) => item.tone !== 'danger')
          .map((item) => (
            <ToastView key={item.id} item={item} onDismiss={dismiss} />
          ))}
      </div>
      <div className={styles.regionUrgent} role="alert" aria-live="assertive" aria-label="Errors">
        {items
          .filter((item) => item.tone === 'danger')
          .map((item) => (
            <ToastView key={item.id} item={item} onDismiss={dismiss} />
          ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastView({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  const tone = item.tone ?? 'info';
  const Icon = ICONS[tone];

  useEffect(() => {
    if (tone === 'danger') return undefined; // errors stay until dismissed
    const timer = window.setTimeout(() => onDismiss(item.id), AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [item.id, tone, onDismiss]);

  return (
    <div className={[styles.toast, styles[tone]].join(' ')}>
      <Icon className={styles.icon} aria-hidden />
      <p className={styles.message}>{item.message}</p>
      {item.action ? (
        <button
          type="button"
          className={styles.action}
          onClick={() => {
            item.action?.onClick();
            onDismiss(item.id);
          }}
        >
          {item.action.label}
        </button>
      ) : null}
      <button
        type="button"
        className={styles.close}
        aria-label="Dismiss notification"
        onClick={() => onDismiss(item.id)}
      >
        <X aria-hidden />
      </button>
    </div>
  );
}
