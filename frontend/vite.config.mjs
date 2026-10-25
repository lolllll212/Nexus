import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// Cosmos MPA pipeline (index.html / holo.html / chat.html / workspace.html).
// The React app in web/ has its own Vite config building to frontend/dist —
// outputs are deliberately separate (this one: frontend/dist-cosmos).
const here = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  appType: 'mpa',
  server: {
    port: 5174,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/chat': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist-cosmos',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(here, 'index.html'),
        holo: resolve(here, 'holo.html'),
        chat: resolve(here, 'chat.html'),
        workspace: resolve(here, 'workspace.html'),
      },
    },
  },
});
