import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {defineConfig} from 'vite';

const __dirname = dirname(fileURLToPath(import.meta.url));
const defaultPort = Number(process.env.ANKI_AUTOFILLER_VITE_PORT || 4173);

export default defineConfig({
  root: __dirname,
  build: {
    outDir: resolve(__dirname, '../autofiller/static'),
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, 'src/main.js'),
      output: {
        entryFileNames: 'app.js',
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: Number.isFinite(defaultPort) ? defaultPort : 4173,
    strictPort: true,
  },
});
