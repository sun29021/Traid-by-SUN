import { createContext, useContext } from 'react';

export interface ToastInput {
  message: string;
  tone?: 'info' | 'success' | 'danger';
  action?: { label: string; onClick: () => void };
}

export const ToastContext = createContext<{ toast: (input: ToastInput) => void } | null>(null);

export function useToast(): (input: ToastInput) => void {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside <ToastProvider>');
  return context.toast;
}
