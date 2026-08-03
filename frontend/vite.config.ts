import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.indexOf("node_modules/motion") >= 0 || id.indexOf("node_modules/framer-motion") >= 0) return "motion-ui";
          if (id.indexOf("node_modules/react") >= 0) return "react";
        }
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/media": "http://127.0.0.1:8080"
    }
  }
});
