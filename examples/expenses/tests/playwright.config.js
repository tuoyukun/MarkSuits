import { createHash } from "node:crypto";
import { defineConfig, devices } from "@playwright/test";

// One port per checkout, so tickets in different worktrees can test at the same time.
// Override with PORT=<n>.
const port = Number(process.env.PORT) ||
  8100 + (createHash("sha1").update(process.cwd()).digest().readUInt16BE(0) % 800);

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Serves the app as static files; each test gets a fresh browser context, so empty localStorage.
  webServer: {
    command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory ../frontend`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
  },
});
