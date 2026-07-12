/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: false,
      open: false,
      proxy: {
        // All /api/* requests are proxied to the backend API Gateway (default :8000)
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
          ws: true,
          // Don't rewrite — keep /api prefix so backend can route correctly
          rewrite: (path) => path
        }
      }
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          manualChunks: {
            'vue-vendor': ['vue', 'vue-router', 'pinia', 'vue-i18n'],
            'naive-vendor': ['naive-ui'],
            'echarts-vendor': ['echarts', 'vue-echarts'],
            'vueflow-vendor': ['@vue-flow/core', '@vue-flow/controls', '@vue-flow/background', '@vue-flow/minimap']
          }
        }
      }
    },
    optimizeDeps: {
      include: [
        'vue',
        'vue-router',
        'vue-i18n',
        'pinia',
        'axios',
        'naive-ui',
        'echarts',
        'vue-echarts'
      ]
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./tests/setup.ts'],
      // Include both .spec.ts (project convention) and .test.ts (P21 P2 P2 task spec)
      include: [
        'tests/**/*.spec.ts',
        'tests/**/*.test.ts',
        'src/components/__tests__/**/*.spec.ts',
        'src/**/__tests__/**/*.spec.ts'
      ],
      exclude: ['tests/e2e/**', 'node_modules/**', 'dist/**'],
      css: false,
      // Keep tests fast — single thread, no isolation overhead for unit specs.
      pool: 'threads',
      poolOptions: {
        threads: { singleThread: true }
      }
    }
  }
})