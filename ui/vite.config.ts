import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { nodePolyfills } from "vite-plugin-node-polyfills";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  base: "/app/",
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    // Replica o roteamento do Caddy (prod e environments/development) localmente:
    // permite rodar `npm run dev` standalone com api/chatbot ouvindo nas portas nativas
    // sem precisar setar VITE_BASE_URL. Cobre o caso same-origin que o codigo usa por default.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/chat": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
  plugins: [
    nodePolyfills(),
    react(),
    mode === "development" && componentTagger(),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
