import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // API_TARGET=https://srv1.tailf3b6bc.ts.net previews the UI against the live server (over Tailscale)
    proxy: { "/api": { target: process.env.API_TARGET ?? "http://localhost:8010", changeOrigin: true } },
  },
});
