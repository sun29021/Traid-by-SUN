import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { Button } from '../Button/Button';
import { Dialog } from './Dialog';

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Delete profile</Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Delete profile?"
        size="sm"
        footer={<Button onClick={() => setOpen(false)}>Cancel</Button>}
      >
        This cannot be undone.
      </Dialog>
    </>
  );
}

describe('Dialog', () => {
  it('opens as a labelled dialog and returns focus on close', () => {
    render(<Harness />);
    const trigger = screen.getByRole('button', { name: 'Delete profile' });
    trigger.focus();

    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Delete profile?' });
    expect(dialog).toHaveAttribute('open');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(dialog).not.toHaveAttribute('open');
    expect(trigger).toHaveFocus();
  });

  it('closes on Escape (cancel event) through onClose', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete profile' }));
    const dialog = screen.getByRole('dialog');

    fireEvent(dialog, new Event('cancel', { cancelable: true }));

    expect(dialog).not.toHaveAttribute('open');
  });
});
