import { createHash } from "node:crypto";
import { defineConfig, devices } from "@playwright/test";

// One port per checkout, so tickets in different worktrees can test at the same time.
// Override with PORT=<n>.
const port = Number(process.env.PORT) ||
  8100 + (createHash("sha1").update(process.cwd()).digest().readUInt16BE(0) % 800);

export default defineConfig({
  testDir: ".",  // the suite root: tickets/<id>/ and regression/ both live here
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `python3 ../backend/server.py --port ${port}`,
    url: `http://127.0.0.1:${port}/api/todos`,
    reuseExistingServer: false,
  },
});
