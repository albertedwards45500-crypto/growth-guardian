/**
 * @file: vite.config.ts
 * @description: Vite 构建配置：Vue 插件与开发服务器 /api 代理至后端 FastAPI。
 */
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

// 导出 Vite 配置对象
export default defineConfig({
  // 启用 Vue 3 单文件组件支持
  plugins: [vue()],
  resolve: {
    // @ 别名指向 src 目录
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  // 开发服务器配置
  server: {
    // 前端开发端口
    port: 5173,
    // 代理规则：所有 /api 请求转发到本地 FastAPI 后端
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8300',
        changeOrigin: true
      }
    }
  }
})
