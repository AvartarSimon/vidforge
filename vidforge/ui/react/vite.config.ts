import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// dev-only: proxy API/media calls to the Python backend (`vidforge ui <project> --port 8765`)
// so the browser only ever talks to this Vite origin — no CORS, no backend changes needed.
// Both ports are overridable via env vars — handy for running a second, fully independent
// dev-server+backend pair (e.g. to try changes against a scratch project without touching
// whatever project is open in your main 5175/8765 instance).
const backendPort = process.env.VITE_BACKEND_PORT || '8765'
const devPort = Number(process.env.VITE_PORT) || 5175

export default defineConfig({
  plugins: [react()],
  server: {
    port: devPort,
    proxy: {
      '/api': { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true },
      '/files': { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true },
    },
  },
})
