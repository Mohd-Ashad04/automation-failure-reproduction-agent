// @ts-check
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: 'verify.spec.js',
  timeout: 10000,
  retries: 0,
  workers: 1,
  use: {
    headless: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  reporter: [
    ['json', { outputFile: 'real_playwright_report.json' }],
  ],
});

