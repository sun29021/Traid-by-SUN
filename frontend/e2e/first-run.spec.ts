import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, test } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

async function seriousA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.help} → ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
}

test('first run shows Welcome, then continues to the requested page', async ({ page }) => {
  await page.goto('/history');

  await expect(page).toHaveURL(/\/welcome\?next=%2Fhistory$/);
  await expect(page.getByRole('heading', { name: 'Traid' })).toBeVisible();
  await expect(page.getByText(/^Running · v/)).toBeVisible();
  // The E2E server uses the real models folder, so the engine reports itself ready.
  await expect(page.getByText(/^Ready · (CPU|GPU)/)).toBeVisible();
  await expect(page.getByText('Traid · Designed & developed by Xavier Sun')).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);

  const start = page.getByRole('button', { name: 'Start using Traid' });
  await expect(start).toBeDisabled();
  await page.getByRole('checkbox', { name: /only edit images I own/ }).check();
  await start.click();

  await expect(page).toHaveURL(/\/history$/);
  await expect(page.getByRole('heading', { level: 1, name: 'History' })).toBeVisible();
});

test('acceptance is remembered and the app shell is accessible', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible();
  await expect(page.getByText('by Xavier Sun')).toBeVisible();
  await expect(page.getByText('Engine online · v0.1.0')).toBeAttached();
  expect(await seriousA11yViolations(page)).toEqual([]);
});

test('keyboard shortcuts navigate between sections', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible();

  await page.keyboard.press('g');
  await page.keyboard.press('s');

  await expect(page).toHaveURL(/\/settings$/);
  await expect(page).toHaveTitle('Settings — Traid');
});
