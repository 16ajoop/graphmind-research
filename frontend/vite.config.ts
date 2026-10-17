import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The UI only talks to "/api/...". In development Vite forwards those requests to FastAPI on :8000,
// so the browser sees one origin and no CORS setup is needed. 127.0.0.1, not localhost: on Windows
// localhost can resolve to IPv6 (::1) while uvicorn listens on IPv4 only.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { chunkSizeWarningLimit: 900 },     // one bundle with React Flow is ~560 kB; fine for a local app
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
