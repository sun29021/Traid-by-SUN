import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from './Button';

describe('Button', () => {
  it('defaults to a non-submitting secondary button', () => {
    render(<Button>Cancel</Button>);

    const button = screen.getByRole('button', { name: 'Cancel' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button.className).toContain('secondary');
  });

  it('is disabled and busy while loading', () => {
    render(
      <Button variant="primary" loading>
        Generate
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Generate' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });
});
