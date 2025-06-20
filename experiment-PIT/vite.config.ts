import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1'
  },
  base: '/experimenting/8/',
  build: {
    outDir: process.env.BUILD_PATH || 'dist', // Use BUILD_PATH from .env or default to 'dist'
  },
})
