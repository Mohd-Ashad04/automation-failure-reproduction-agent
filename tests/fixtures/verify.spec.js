const { test, expect } = require('@playwright/test');
const path = require('path');

const targetUrl = 'file://' + path.resolve(__dirname, 'index.html').replace(/\\/g, '/');

test.describe('AFRA Local Verification Suite', () => {
  test('passing test: heading has expected text', async ({ page }) => {
    await page.goto(targetUrl);
    const heading = page.locator('#app-heading');
    await expect(heading).toHaveText('AFRA Verification Target');
  });

  test('failing test: status has expected text', async ({ page }) => {
    await page.goto(targetUrl);
    const status = page.locator('#app-status');
    // Deliberately failing assertion with predictable message:
    await expect(status).toHaveText('STATUS: NONEXISTENT_FAILING_STATE', { timeout: 2000 });
  });
});

