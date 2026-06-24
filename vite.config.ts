import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  plugins: [react()],
  base: './',
  root: 'src/renderer',
  publicDir: '../../public',
  build: {
    outDir: '../../dist/renderer',
    emptyOutDir: true,
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      input: path.resolve(__dirname, 'src/renderer/index.html'),
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
        // 代码分割：按供应商/UI库/页面分块
        manualChunks(id) {
          // 供应商包: node_modules中的核心库
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom') || id.includes('scheduler')) {
              return 'vendor-react';
            }
            if (id.includes('pixi') || id.includes('pixi-live2d')) {
              return 'vendor-pixi';
            }
            if (id.includes('three') || id.includes('@react-three')) {
              return 'vendor-three';
            }
            if (id.includes('leaflet') || id.includes('react-leaflet')) {
              return 'vendor-leaflet';
            }
            if (id.includes('recharts') || id.includes('d3')) {
              return 'vendor-charts';
            }
            if (id.includes('framer-motion')) {
              return 'vendor-animation';
            }
            if (id.includes('lucide')) {
              return 'vendor-icons';
            }
            if (id.includes('lodash') || id.includes('date-fns') || id.includes('clsx') || id.includes('tailwind')) {
              return 'vendor-utils';
            }
            // 剩余node_modules
            return 'vendor-other';
          }
          // 页面级懒加载：大页面独立分包
          if (id.includes('/pages/')) {
            const pageMatch = id.match(/\/pages\/(\w+)\.tsx/);
            if (pageMatch) {
              const pageName = pageMatch[1];
              const bigPages = ['OmniGenStudio', 'ProductionWorkbench', 'AnnotationSystem',
                'AIGCWorkbenchPro', 'InformationCenter', 'CommercialAssets', 'NanobotController',
                'FiftyOneManager', 'CanvasStudio', 'WorldMonitor'];
              if (bigPages.includes(pageName)) {
                return `page-${pageName}`;
              }
            }
          }
        },
      },
      // 外部化 live2dcubismcore.min.js - 这是一个 UMD 库，不能被 ES 模块打包
      external: ['./live2d/live2dcubismcore.min.js', '/live2d/live2dcubismcore.min.js'],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src/renderer'),
      '@shared': path.resolve(__dirname, 'src/shared'),
    },
  },
  define: {
    global: 'globalThis',
  },
  optimizeDeps: {
    esbuildOptions: {
      define: {
        global: 'globalThis',
      },
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    host: '0.0.0.0',
    hmr: {
      clientPort: 5173,
    },
    cors: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path,
      },
      '/airi': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: true,
      },
      '/omni': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: true,
      },
      '/health': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: true,
      },
      '/metrics': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: true,
      },
      '/ws': {
        target: 'ws://localhost:8001',
        ws: true,
      },
    },
  },
  preview: {
    headers: {
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'X-XSS-Protection': '1; mode=block',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws://localhost:* http://localhost:* http://localhost:8001;",
    },
  },
});
