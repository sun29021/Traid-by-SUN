import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DropZone } from './DropZone';

function file(name: string, type: string): File {
  return new File(['x'], name, { type });
}

describe('DropZone', () => {
  it('delivers accepted files and reports rejected ones', () => {
    const onFiles = vi.fn();
    const onReject = vi.fn();
    render(<DropZone title="Drop images" multiple onFiles={onFiles} onReject={onReject} />);

    const png = file('a.png', 'image/png');
    const pdf = file('b.pdf', 'application/pdf');
    fireEvent.drop(screen.getByText('Drop images').parentElement as HTMLElement, {
      dataTransfer: { files: [png, pdf], items: [] },
    });

    expect(onFiles).toHaveBeenCalledWith([png]);
    expect(onReject).toHaveBeenCalledWith([pdf]);
  });

  it('keeps only the first file when multiple is off', () => {
    const onFiles = vi.fn();
    render(<DropZone title="Drop a target image" onFiles={onFiles} />);
    const first = file('a.jpg', 'image/jpeg');

    fireEvent.drop(screen.getByText('Drop a target image').parentElement as HTMLElement, {
      dataTransfer: { files: [first, file('b.jpg', 'image/jpeg')], items: [] },
    });

    expect(onFiles).toHaveBeenCalledWith([first]);
  });

  it('is usable from the keyboard through the Browse button', () => {
    render(<DropZone title="Drop images" hint="JPEG, PNG or TIFF" onFiles={vi.fn()} />);

    const browse = screen.getByRole('button', { name: 'Browse files' });
    expect(browse).toHaveAccessibleDescription('JPEG, PNG or TIFF');
  });
});
