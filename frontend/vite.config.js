import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0', // Permits network binding mapping across Docker network layers
    watch: {
      usePolling: true, // Forces file monitoring checks on system mounts
    },
  },
});