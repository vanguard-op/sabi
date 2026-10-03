import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The console talks to the API gateway through a relative `/v1` base. In dev the
// proxy forwards to the local API so the browser stays same-origin and the
// HttpOnly staff session cookie is sent without CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/v1': {
        target: process.env.SABI_API_ORIGIN ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
