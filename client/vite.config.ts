import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // `npm run dev` against the API of `docker compose up` (port 3000).
    proxy: { "/api": "http://localhost:3000" },
  },
  test: {
    environment: "node",
  },
});
