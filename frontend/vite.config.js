import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": globalThis.process?.env?.VITE_API_TARGET || "http://127.0.0.1:8000",
    },
    watch: {
      usePolling: true,
    },
  },
});
