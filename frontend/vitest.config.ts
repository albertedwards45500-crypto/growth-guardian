/**
 * @file: vitest.config.ts
 * @description: Vitest 测试配置：jsdom 环境与测试文件匹配规则，独立于 vite.config.ts。
 */
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

// 导出 Vitest 配置对象
export default defineConfig({
  // 测试环境中同样启用 Vue SFC 编译
  plugins: [vue()],
  resolve: {
    // 测试中可使用 @ 别名引用 src 目录
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  test: {
    // 测试运行环境：jsdom 模拟浏览器 DOM
    environment: 'jsdom',
    // 测试文件匹配模式
    include: ['tests/**/*.spec.ts'],
    // 关闭文件级并行：本机内存有限，多 worker 并发易触发堆内存溢出
    fileParallelism: false
  }
})
