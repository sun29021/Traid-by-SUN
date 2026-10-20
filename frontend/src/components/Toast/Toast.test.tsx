import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from './Toast';
import { type ToastInput, useToast } from './toastContext';

function Trigger({ input }: { input: ToastInput }) {
  const toast = useToast();
  return (
    <button type="button" onClick={() => toast(input)}>
      Show
    </button>
  );
}

describe('Toast', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('auto-dismisses info toasts after 5 seconds', () => {
    render(
      <ToastProvider>
        <Trigger input={{ message: 'Export saved', tone: 'success' }} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Show' }));
    expect(screen.getByText('Export saved')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(5000));

    expect(screen.queryByText('Export saved')).not.toBeInTheDocument();
  });

  it('keeps error toasts until dismissed, in the assertive region', () => {
    render(
      <ToastProvider>
        <Trigger input={{ message: 'Disk full', tone: 'danger' }} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Show' }));
    act(() => vi.advanceTimersByTime(60_000));

    const message = screen.getByText('Disk full');
    expect(message.closest('[aria-live]')).toHaveAttribute('aria-live', 'assertive');

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    expect(screen.queryByText('Disk full')).not.toBeInTheDocument();
  });

  it('shows at most three toasts', () => {
    render(
      <ToastProvider>
        <Trigger input={{ message: 'Saved' }} />
      </ToastProvider>,
    );
    const show = screen.getByRole('button', { name: 'Show' });
    for (let i = 0; i < 5; i += 1) fireEvent.click(show);

    expect(screen.getAllByText('Saved')).toHaveLength(3);
  });
});
