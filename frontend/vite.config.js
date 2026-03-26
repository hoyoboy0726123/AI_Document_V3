import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // 修復 react-markdown 的 global is not defined 錯誤
    global: 'globalThis',
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
