import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "json-summary", "json"],
      reportsDirectory: "./coverage",
      // Coverage so de src/, excluindo bibliotecas, tipos, mocks e UI components
      // gerados (shadcn/ui). Foco: codigo de produto.
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.d.ts",
        "src/**/*.{test,spec}.{ts,tsx}",
        "src/test/**",
        "src/components/ui/**", // shadcn primitives sao baseline, nao codigo nosso
        "src/main.tsx",
        "src/vite-env.d.ts",
      ],
      // Sem thresholds por enquanto — primeiro estabelece baseline, depois define gate.
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
