import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * R3.5-W2 上游修复 — Vite 配置
 *
 * - React 插件：处理 .tsx 文件
 * - virtual:t8-local-extensions：插件式虚拟模块，提供本地扩展槽位占位
 * - 输入：index.html + imdf-app.tsx（imdf-main.tsx 也会被自动跟踪）
 * - 输出：dist/
 */
export default defineConfig({
  plugins: [
    react(),
    {
      name: 't8-local-extensions',
      resolveId(id) {
        if (id === 'virtual:t8-local-extensions') {
          return '\0virtual:t8-local-extensions';
        }
        return null;
      },
      load(id) {
        if (id === '\0virtual:t8-local-extensions') {
          return `
            import React from 'react';
            export function LocalModalSlot() { return null; }
            export function LocalTopbarSlot() { return null; }
          `;
        }
        return null;
      },
    },
  ],
  root: '.',
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        // 把 imdf-app.tsx 作为附加入口（vite 自动跟踪其依赖）
        app: path.resolve(__dirname, 'src/imdf-app.tsx'),
      },
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  define: {
    global: 'globalThis',
    __APP_VERSION__: JSON.stringify(require('./package.json').version),
  },
});
