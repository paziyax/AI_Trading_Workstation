import { defineConfig, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const PORT = 8123;
const BASE_URL = `http://127.0.0.1:${PORT}`;

const testDir = path.resolve(__dirname);
const repoRoot = path.resolve(testDir, "..");
const tmpDir = path.join(testDir, ".tmp");

// A fresh SQLite file per run means the database always seeds the ten default
// tickers and the $10,000 balance, so specs never inherit another run's state.
mkdirSync(tmpDir, { recursive: true });
const dbPath = path.join(tmpDir, `e2e-${Date.now()}-${process.pid}.db`);

export default defineConfig({
  testDir: "./e2e",
  // One worker: the app is single-user and every spec shares one SQLite file.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  globalTeardown: "./global-teardown.ts",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    // The console shims for uvicorn are blocked by Smart App Control on this
    // machine, so the module form is used.
    command: `uv run --project . --module uvicorn app.main:app --host 127.0.0.1 --port ${PORT} --log-level warning`,
    cwd: path.join(repoRoot, "backend"),
    url: `${BASE_URL}/api/health`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      LLM_MOCK: "true",
      MARKET_DATA_SOURCE: "simulator",
      MASSIVE_API_KEY: "",
      FINALLY_DB_PATH: dbPath,
      STATIC_DIR: path.join(repoRoot, "frontend", "out"),
      PYTHONUNBUFFERED: "1",
    },
  },
});
