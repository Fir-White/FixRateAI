import playwright from "@playwright/test";

const { defineConfig } = playwright;

export default defineConfig({
  testDir: "../tests/web/e2e",
  tsconfig: "../tests/web/tsconfig.json",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  reporter: "list",
  use: { baseURL: process.env.FIXRATE_BASE_URL, channel: "chrome", headless: true },
});
