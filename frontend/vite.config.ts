import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => ({
  root: fileURLToPath(new URL(".", import.meta.url)),
  envDir: fileURLToPath(new URL("..", import.meta.url)),
  plugins: [react(), tailwindcss()],
  resolve: {
    dedupe: mode === "test" ? [
      "react", "react-dom", "react-router-dom", "vitest",
      "@testing-library/react", "@testing-library/user-event", "@testing-library/jest-dom",
    ] : [],
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    fs: { allow: [fileURLToPath(new URL(mode === "test" ? ".." : ".", import.meta.url))] },
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    include: ["../tests/web/unit/**/*.{test,spec}.{ts,tsx}"],
    environment: "jsdom",
    env: { VITE_DEMO_MODE: "true" },
    setupFiles: fileURLToPath(new URL("../tests/web/setup.ts", import.meta.url)),
    deps: {
      moduleDirectories: ["node_modules", fileURLToPath(new URL("./node_modules", import.meta.url))],
    },
    css: true,
  },
}));
