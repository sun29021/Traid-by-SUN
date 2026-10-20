import { fileURLToPath } from 'node:url';

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * PRD journey J2 with the real engine: create a profile in the UI, upload two real-looking
 * photos, let PP-OCR + segmentation extract glyphs, review them with the keyboard, and see
 * the profile become Ready. Runs after first-run.spec.ts (shared server, AUP accepted).
 */
test.describe.configure({ mode: 'serial' });

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

test.beforeEach(async ({ page, request }) => {
  // Make the spec independent of first-run.spec.ts ordering.
  await request.post('/api/v1/system/welcome', {
    data: { accept_aup: true },
    headers: { 'X-Traid-Client': 'web' },
  });
  await page.goto('/profiles');
});

test('train a profile from reference photos to Ready', async ({ page }) => {
  await page.getByRole('button', { name: 'New profile' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'New Style Profile' });
  await dialog.getByLabel('Name').fill('E2E receipt tokens');
  await dialog.getByText('Print', { exact: true }).click();
  await dialog.getByLabel('Character set').selectOption('custom');
  await dialog.getByLabel('Custom characters').fill('A7-204913');
  await dialog.getByRole('button', { name: 'Create profile' }).click();

  // Lands on the References tab of the new profile.
  await expect(page).toHaveURL(/\/profiles\/[^/]+\/references$/);
  await page
    .locator('input[type=file]')
    .setInputFiles([fixture('token-1.jpg'), fixture('token-2.jpg')]);
  await expect(page.getByText('2 added')).toBeVisible();

  // Extraction with the real models (CPU or GPU) finishes and fills the glyph bank.
  const cards = page.getByRole('list', { name: 'Reference images' }).getByRole('button');
  await expect(cards).toHaveCount(2);
  await expect(cards.filter({ hasText: 'Processed' })).toHaveCount(2, { timeout: 60_000 });
  await expect(cards.first()).toContainText('9 glyphs');

  // Keyboard review: select everything and confirm.
  await page.getByRole('tab', { name: 'Glyphs' }).click();
  const options = page.getByRole('option');
  await expect(options).toHaveCount(18);
  await options.first().click();
  await page.keyboard.press('Control+a');
  await expect(page.getByText('18 selected')).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page.getByText('18 glyphs confirmed')).toBeVisible();

  // Default threshold is 3 per character; two photos give 2 each, so lower it to 2.
  await page.getByRole('tab', { name: 'Settings' }).click();
  await page.getByLabel('Glyphs needed per character').fill('2');
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.getByText('Profile settings saved')).toBeVisible();

  await page.getByRole('tab', { name: 'Coverage' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'E2E receipt tokens' })).toBeVisible();
  await expect(page.locator('header').getByText('Ready', { exact: true })).toBeVisible();
});

test('profile screens have no serious accessibility violations', async ({ page }) => {
  const serious = async () => {
    const results = await new AxeBuilder({ page }).analyze();
    return results.violations
      .filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  };
  await expect(page.getByRole('row', { name: /E2E receipt tokens/ })).toBeVisible();
  expect(await serious()).toEqual([]);

  await page.getByRole('row', { name: /E2E receipt tokens/ }).click();
  for (const tab of ['References', 'Glyphs', 'Coverage', 'Settings']) {
    await page.getByRole('tab', { name: tab }).click();
    await expect(page.getByRole('tab', { name: tab })).toHaveAttribute('aria-selected', 'true');
    await page.waitForLoadState('networkidle');
    expect(await serious(), `${tab} tab`).toEqual([]);
  }
});

test('the profile list shows the trained profile', async ({ page }) => {
  const row = page.getByRole('row', { name: /E2E receipt tokens/ });

  await expect(row).toContainText('Ready');
  await expect(row).toContainText('18 / 18');
  await expect(row).toContainText('100%');
});
