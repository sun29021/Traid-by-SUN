import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Checkbox, Toggle } from '../Checkbox/Checkbox';
import { Select } from '../Select/Select';
import { TextField } from './TextField';

describe('form fields', () => {
  it('labels inputs and links helper and error text', () => {
    render(<TextField label="Profile name" helper="Required" error="Name already used" />);

    const input = screen.getByLabelText('Profile name');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Required Name already used');
  });

  it('labels selects', () => {
    render(
      <Select
        label="Surface type"
        options={[
          { value: 'print', label: 'Print' },
          { value: 'engraved', label: 'Engraved' },
        ]}
      />,
    );

    expect(screen.getByLabelText('Surface type')).toHaveValue('print');
  });

  it('renders toggles as switches', () => {
    render(
      <>
        <Checkbox label="Use auto glyphs" />
        <Toggle label="Metadata marker" />
      </>,
    );

    expect(screen.getByRole('checkbox', { name: 'Use auto glyphs' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Metadata marker' })).toBeInTheDocument();
  });
});
