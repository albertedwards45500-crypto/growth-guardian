/**
 * @file: src/main.ts
 * @description: 应用入口：创建 Vue 实例并挂载 Pinia、路由与全局主题样式。
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/theme.css'

// 创建 Vue 应用实例
const app = createApp(App)

// 挂载状态管理
app.use(createPinia())
// 挂载路由（含全局守卫与 40100 处理注入）
app.use(router)

// 渲染到 #app
app.mount('#app')
