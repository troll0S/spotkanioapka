import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// W trybie dev w Dockerze backend jest pod nazwą usługi, lokalnie pod localhost.
const target = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // host: true = nasłuch na 0.0.0.0, inaczej telefon nie dosięgnie Vite.
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target, changeOrigin: true },
      // ws: true będzie potrzebne dopiero w K1, ale niech stoi od początku.
      "/ws": { target, ws: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
