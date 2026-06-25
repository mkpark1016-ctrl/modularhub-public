import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "strip-localhost-fallback-literal",
      renderChunk(code) {
        return code.includes("http://localhost")
          ? { code: code.replaceAll("http://localhost", "https://modularhub.invalid"), map: null }
          : null;
      },
    },
  ],
});
