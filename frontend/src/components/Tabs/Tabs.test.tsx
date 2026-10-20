import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { TabPanel, Tabs } from './Tabs';

const ITEMS = [
  { id: 'overview', label: 'Overview' },
  { id: 'glyphs', label: 'Glyphs' },
  { id: 'settings', label: 'Settings' },
];

function Harness() {
  const [value, setValue] = useState('overview');
  return (
    <>
      <Tabs label="Profile" idPrefix="p" items={ITEMS} value={value} onChange={setValue} />
      <TabPanel idPrefix="p" id={value}>
        Panel {value}
      </TabPanel>
    </>
  );
}

describe('Tabs', () => {
  it('wires tabs to their panel', () => {
    render(<Harness />);

    const tab = screen.getByRole('tab', { name: 'Overview' });
    const panel = screen.getByRole('tabpanel');
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(tab).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
  });

  it('moves with arrow keys, wraps around and supports Home/End', () => {
    render(<Harness />);
    const overview = screen.getByRole('tab', { name: 'Overview' });

    fireEvent.keyDown(overview, { key: 'ArrowLeft' });
    expect(screen.getByRole('tab', { name: 'Settings' })).toHaveFocus();
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Panel settings');

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Settings' }), { key: 'Home' });
    expect(overview).toHaveFocus();

    fireEvent.keyDown(overview, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Glyphs' })).toHaveAttribute('tabindex', '0');
    expect(overview).toHaveAttribute('tabindex', '-1');
  });
});
