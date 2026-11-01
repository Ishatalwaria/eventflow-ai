import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_API_BASE_URL || "http://localhost:8000";
  return {
    plugins: [react()],
    resolve: { alias: [{ find: /^@\//, replacement: "/src/" }] },
    server: {
      port: 5173,
      proxy: {
        "/api": { target, changeOrigin: true },
        "/health/live": { target, changeOrigin: true },
        "/health/ready": { target, changeOrigin: true },
        "/health/services": { target, changeOrigin: true },
      },
    },
    test: { environment: "jsdom", setupFiles: "./src/test/setup.ts", restoreMocks: true, clearMocks: true },
  };
});
