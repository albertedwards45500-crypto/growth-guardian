/**
 * @file: src/env.d.ts
 * @description: 环境类型声明：Vite 客户端类型与 .vue 单文件组件模块声明。
 */
/// <reference types="vite/client" />

// 声明 .vue 单文件组件的模块类型
declare module '*.vue' {
  // 组件默认导出定义
  import type { DefineComponent } from 'vue'
  // 任意组件的通用类型签名
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const component: DefineComponent<{}, {}, any>
  // 默认导出组件
  export default component
}
