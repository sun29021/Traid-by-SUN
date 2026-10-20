import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { TokenInput } from './TokenInput';
import { validateToken } from './validateToken';

const CHARSET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ- ';

function Harness({ pattern }: { pattern?: string }) {
  const [value, setValue] = useState('');
  return (
    <TokenInput
      label="New token"
      value={value}
      onChange={setValue}
      charset={CHARSET}
      pattern={pattern}
    />
  );
}

describe('validateToken', () => {
  it('lists unique characters outside the charset in order', () => {
    expect(validateToken('A7-q@q', CHARSET).invalidChars).toEqual(['q', '@']);
  });

  it('checks the pattern only when one is set and valid', () => {
    expect(validateToken('A7-204913', CHARSET, '^[A-Z]\\d-\\d{6}$').patternMatches).toBe(true);
    expect(validateToken('A7-2049', CHARSET, '^[A-Z]\\d-\\d{6}$').patternMatches).toBe(false);
    expect(validateToken('A7', CHARSET).patternMatches).toBeNull();
    expect(validateToken('A7', CHARSET, '([').patternMatches).toBeNull();
  });
});

describe('TokenInput', () => {
  it('flags characters outside the charset and links the message', () => {
    render(<Harness />);
    const input = screen.getByLabelText('New token');

    fireEvent.change(input, { target: { value: 'A7 q' } });

    expect(input).toHaveAttribute('aria-invalid', 'true');
    const message = screen.getByRole('alert');
    expect(message).toHaveTextContent("Not in this profile's character set: q");
    expect(input.getAttribute('aria-describedby')).toContain(message.id);
  });

  it('shows the pattern status and the length counter', () => {
    render(<Harness pattern="^[A-Z]\d-\d{6}$" />);
    const input = screen.getByLabelText('New token');

    fireEvent.change(input, { target: { value: 'A7-204913' } });

    expect(screen.getByText('Pattern matches')).toBeInTheDocument();
    expect(screen.getByText('9/64')).toBeInTheDocument();
    expect(input).not.toHaveAttribute('aria-invalid');
  });
});
