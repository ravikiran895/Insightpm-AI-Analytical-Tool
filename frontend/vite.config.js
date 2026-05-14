import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite proxy means the frontend just calls /api/* and Vite forwards to FastAPI
// during dev. In production you'd serve them on the same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
