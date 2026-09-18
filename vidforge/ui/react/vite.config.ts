import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// dev-only: proxy API/media calls to the Python backend (`vidforge ui <project> --port 8765`)
// so the browser only ever talks to this Vite origin — no CORS, no backend changes needed.
// If the backend picked a different port (8765 was busy), edit the proxy target below to match.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/files': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
})
