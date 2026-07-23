import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // In dev the React app lives on :5173 and the backend API on :8080.
      // Vite transparently forwards every /api/* request to the backend.
      // If the backend is not running, the typed API client falls back to
      // in-memory mock data (see src/api/tasksApi.ts), so the UI still works.
      "/api": "http://localhost:8080",
    },
  },
});
