import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/app/',
  server: {
    port: 5173,
    proxy: {
      '/runs': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
      '/schema': 'http://localhost:8001',
    },
  },
  build: {
    outDir: '../src/ui',
    emptyOutDir: true,
  },
})
