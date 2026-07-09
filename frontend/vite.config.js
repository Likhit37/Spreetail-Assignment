import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages serves this project at /Spreetail-Assignment/ (a subpath), so the
// production build needs that base for asset URLs. Local dev stays at root.
// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/Spreetail-Assignment/" : "/",
  plugins: [react()],
}));
