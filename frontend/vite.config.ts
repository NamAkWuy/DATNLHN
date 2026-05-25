import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Rewrite Location header trong response của backend từ tuyệt đối
// (http://localhost:8000/...) → tương đối (/...). Khi backend trả 307 vì
// thiếu/dư dấu / cuối URL, browser sẽ follow redirect cùng origin (localhost:3000)
// thay vì cross-origin sang :8000 — qua đó giữ nguyên header Authorization.
const rewriteLocation = (proxy: any) => {
  proxy.on('proxyRes', (proxyRes: any) => {
    const loc = proxyRes.headers?.location
    if (typeof loc === 'string') {
      proxyRes.headers.location = loc.replace(/^https?:\/\/[^/]+/, '')
    }
  })
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: rewriteLocation,
      },
      '/uploads': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: rewriteLocation,
      },
    },
  },
})
