import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Phase 2: the frontend had no tests at all. jsdom rather than a browser —
  // what is worth testing here is logic that fails silently (a CSRF header that
  // stops being sent, an auth bootstrap that stops running), not pixels.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    include: ['src/**/*.test.{js,jsx}'],
  },
  server: {
    port: 5173,
    proxy: {
      // Only the auth and live-run routers are mounted under /api; the rest sit
      // at the root (see CLAUDE.md section 8). Every one of those prefixes has
      // to be proxied explicitly, or the dev server answers with index.html and
      // the call fails as a JSON parse error rather than a 404.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/scenarios': { target: 'http://localhost:8000', changeOrigin: true },
      '/jobs': { target: 'http://localhost:8000', changeOrigin: true },
      '/results': { target: 'http://localhost:8000', changeOrigin: true },
      '/evaluate': { target: 'http://localhost:8000', changeOrigin: true },
      '/models': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
