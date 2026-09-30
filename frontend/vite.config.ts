import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the dashboard talks to a local FastAPI (default :8000).
// In production it is served from the same origin as the API, so every
// request is a relative /api/v1/... path and no CORS is involved.
const apiTarget = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
      "/docs": apiTarget,
      "/openapi.json": apiTarget,
    },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 900,
  },
});
