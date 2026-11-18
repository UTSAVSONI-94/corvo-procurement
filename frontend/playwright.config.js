import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30 * 1000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'cd .. && ./venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/api/policies',
      reuseExistingServer: true,
      timeout: 30000,
    },
    {
      command: './node_modules/.bin/vite --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
});
