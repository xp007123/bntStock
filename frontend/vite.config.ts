/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 默认把 /api 代理到 8000。想连另一个本地后端：npm run dev -- --mode api-8001
export default defineConfig(({ mode }) => {
  const apiPort = /^api-(\d+)$/.exec(mode)?.[1] ?? '8000'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { '/api': `http://127.0.0.1:${apiPort}` },
    },
    build: {
      chunkSizeWarningLimit: 900,
      rollupOptions: { output: { manualChunks: { echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'] } } },
    },
    test: { environment: 'jsdom' },
  }
})
