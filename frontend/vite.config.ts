import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") }
  },
  server: { host: "0.0.0.0", proxy: { "/dashboard": "http://localhost:8000", "/ws": { target: "ws://localhost:8000", ws: true } } },
  optimizeDeps: {
    exclude: ["maplibre-gl"]
  },
  define: {
    "process.env.NODE_ENV": JSON.stringify(process.env.NODE_ENV || "development")
  }
});
