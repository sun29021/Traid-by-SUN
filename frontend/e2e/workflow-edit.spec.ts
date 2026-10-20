import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import AxeBuilder from '@axe-core/playwright';
import { type APIRequestContext, expect, test } from '@playwright/test';

/**
 * PRD journey J3 with the real engine: drop a target photo on Home, let Traid find the
 * token, type the new value, generate, accept and export. The profile is trained through
 * the API first so this spec does not depend on the order of the other specs.
 */
test.describe.configure({ mode: 'serial' });

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));
const headers = { 'X-Traid-Client': 'web' };
const PROFILE = 'E2E editor tokens';

async function readyProfile(request: APIRequestContext): Promise<string> {
  await request.post('/api/v1/system/welcome', { data: { accept_aup: true }, headers });
  const existing = await request.get('/api/v1/profiles?archived=all');
  const found = ((await existing.json()) as { data: { id: string; name: string }[] }).data.find(
    (p) => p.name === PROFILE,
  );
  if (found) return found.id;

  const created = await request.post('/api/v1/profiles', {
    headers,
    data: { name: PROFILE, surface_type: 'print', charset: 'A7-204913', ready_threshold: 2 },
  });
  const profileId = ((await created.json()) as { data: { id: string } }).data.id;
  const upload = await request.post(`/api/v1/profiles/${profileId}/references`, {
    headers,
    multipart: {
      files: {
        name: 'token-1.jpg',
        mimeType: 'image/jpeg',
        buffer: readFileSync(fixture('token-1.jpg')),
      },
    },
  });
  expect(upload.status()).toBe(202);
  const second = await request.post(`/api/v1/profiles/${profileId}/references`, {
    headers,
    multipart: {
      files: {
        name: 'token-2.jpg',
        mimeType: 'image/jpeg',
        buffer: readFileSync(fixture('token-2.jpg')),
      },
    },
  });
  expect(second.status()).toBe(202);
  await expect
    .poll(
      async () => {
        const response = await request.get(`/api/v1/profiles/${profileId}`);
        return ((await response.json()) as { data: { status: string } }).data.status;
      },
      { timeout: 90_000 },
    )
    .not.toBe('training');
  const glyphs = await request.get(`/api/v1/profiles/${profileId}/glyphs?limit=200`);
  const ids = ((await glyphs.json()) as { data: { id: string }[] }).data.map((g) => g.id);
  await request.post(`/api/v1/profiles/${profileId}/glyphs/bulk`, {
    headers,
    data: { ids, action: 'confirm' },
  });
  return profileId;
}

test('drop a photo, generate a new token, accept and export', async ({ page, request }) => {
  test.setTimeout(180_000);
  await readyProfile(request);

  await page.goto('/');
  await page.getByLabel('Style Profile').selectOption({ label: `${PROFILE} · Ready` });
  // 1. Drop the target image.
  await page.locator('input[type=file]').setInputFiles(fixture('target-1.jpg'));
  await expect(page).toHaveURL(/\/editor\/[^/]+$/);

  // Detection preselects the token.
  const regions = page.getByRole('complementary', { name: 'Text regions' });
  await expect(regions.getByRole('button', { pressed: true })).toContainText('A7-204913', {
    timeout: 60_000,
  });
  await expect(page.getByText('Old token')).toBeVisible();

  // 2. Type the new token. 3. Generate (Ctrl+Enter).
  const token = page.getByLabel('New token');
  await token.fill('A7-204931');
  await token.press('Control+Enter');

  const quality = page.getByRole('region', { name: 'Quality' });
  await expect(quality).toBeVisible({ timeout: 90_000 });
  await expect(quality.getByText('OCR read-back')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Edited result' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('editor-result.png') });

  const serious = (await new AxeBuilder({ page }).analyze()).violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);

  // 4. Accept. 5. Export.
  await page.getByRole('button', { name: 'Accept' }).click();
  await expect(page.getByText('Result accepted')).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export' }).click();
  expect((await download).suggestedFilename()).toBe('target-1_A7-204931.jpg');

  // The job shows up on Home.
  await page.goto('/');
  await expect(page.getByRole('row', { name: /A7-204913 → A7-204931/ })).toContainText('Accepted');
});

test('adjustments re-render and can be undone', async ({ page, request }) => {
  test.setTimeout(180_000);
  await readyProfile(request);
  await page.goto('/');
  await page.getByLabel('Style Profile').selectOption({ label: `${PROFILE} · Ready` });
  await page.locator('input[type=file]').setInputFiles(fixture('target-1.jpg'));
  await expect(page.getByLabel('New token')).toBeVisible({ timeout: 60_000 });
  await expect(
    page
      .getByRole('complementary', { name: 'Text regions' })
      .getByRole('button', { pressed: true }),
  ).toBeVisible({ timeout: 60_000 });
  await page.getByLabel('New token').fill('A7-204931');
  await page.getByRole('button', { name: 'Generate' }).click();
  await expect(page.getByRole('region', { name: 'Quality' })).toBeVisible({ timeout: 90_000 });

  const first = await page.getByRole('img', { name: 'Edited result' }).getAttribute('src');
  const ink = page.getByRole('spinbutton', { name: 'Ink tone' });
  await ink.fill('0.5');
  await ink.press('Enter');
  await expect
    .poll(() => page.getByRole('img', { name: 'Edited result' }).getAttribute('src'), {
      timeout: 60_000,
    })
    .not.toBe(first);
  await expect(page.getByText('1 changed')).toBeVisible();

  await page.getByRole('application', { name: /Image canvas/ }).focus();
  await page.keyboard.press('Control+z');
  await expect(page.getByText('1 changed')).toBeHidden();
});

test('a 10-value batch renders, accepts the passed items and exports a ZIP', async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);
  await readyProfile(request);
  // The first test left an accepted edit to use as the template.
  await page.goto('/batch');
  await expect(page.getByLabel('Template edit')).toBeVisible();
  const values = [
    'A7-204193',
    'A7-209413',
    'A7-219403',
    'A7-230419',
    'A7-341920',
    'A7-402913',
    'A7-913024',
    'A7-120394',
    'A7-304921',
    'A7-490213',
  ];
  await page.getByLabel(/Token values/).fill([...values, values[0]].join('\n'));
  const check = page.getByRole('region', { name: 'Check' });
  await expect(check).toContainText('Valid10');
  await expect(check).toContainText('Duplicates (skipped)1');

  await page.getByRole('button', { name: 'Run batch (10)' }).click();
  await expect(page).toHaveURL(/\/batch\/[^/]+$/);
  await expect(page.getByText('Completed', { exact: true })).toBeVisible({ timeout: 180_000 });
  await expect(page.getByRole('list', { name: /Batch items/ }).getByRole('listitem')).toHaveCount(
    10,
  );

  await page.getByRole('button', { name: /Accept all passed/ }).click();
  await expect(page.getByText(/items accepted/)).toBeVisible();
  await page.getByRole('button', { name: /Export accepted/ }).click();
  await expect(page.getByText('The ZIP is ready.')).toBeVisible({ timeout: 60_000 });
});
