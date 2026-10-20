import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { AdjustmentField } from './AdjustmentField';

function Harness() {
  const [value, setValue] = useState(0);
  return (
    <AdjustmentField
      label="Blur"
      value={value}
      onChange={setValue}
      min={-2}
      max={2}
      step={0.1}
      defaultValue={0}
      unit="σ"
    />
  );
}

describe('AdjustmentField', () => {
  it('clamps typed values and marks the field as changed', () => {
    render(<Harness />);
    const number = screen.getByRole('spinbutton', { name: /^Blur/ });

    fireEvent.change(number, { target: { value: '5' } });

    expect(number).toHaveValue(2);
    expect(screen.getByText('(changed)')).toBeInTheDocument();
  });

  it('resets with the button or a double-click on the slider', () => {
    render(<Harness />);
    const slider = screen.getByRole('slider', { name: 'Blur' });

    fireEvent.change(slider, { target: { value: '1.5' } });
    expect(screen.getByRole('spinbutton', { name: /^Blur/ })).toHaveValue(1.5);

    fireEvent.click(screen.getByRole('button', { name: 'Reset Blur' }));
    expect(screen.getByRole('spinbutton', { name: /^Blur/ })).toHaveValue(0);

    fireEvent.change(slider, { target: { value: '-1' } });
    fireEvent.doubleClick(slider);
    expect(screen.getByRole('spinbutton', { name: /^Blur/ })).toHaveValue(0);
  });
});
