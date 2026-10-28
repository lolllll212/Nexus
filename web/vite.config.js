import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const webRoot = fileURLToPath(new URL('.', import.meta.url));

const devProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/v1': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/docs': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/openapi.json': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  // Browser code connects same-origin to /bridge; Vite upgrades it to
  // the local IDE bridge. This also works behind the live-preview host.
  '/bridge': {
    target: 'ws://127.0.0.1:8765',
    ws: true,
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/bridge(?=\/|$)/, '') || '/',
  },
};

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  build: {
    outDir: '../frontend/dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        // Workplace OS remains the root product surface.
        workplace: resolve(webRoot, 'index.html'),
        // Chat is a separate Vite page/entry so it can be developed and
        // loaded without mounting the Workplace OS shell.
        chat: resolve(webRoot, 'chat.html'),
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: true,
    proxy: devProxy,
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: true,
    proxy: devProxy,
  },
});
