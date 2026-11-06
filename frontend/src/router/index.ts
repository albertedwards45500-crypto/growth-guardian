/**
 * @file: src/router/index.ts
 * @description: 路由表与全局守卫：/login /register 公开，其余路由需令牌，同时注入 40100 处理。
 */

import { createRouter, type Router } from 'vue-router'
import { createWebHistory, type RouterHistory } from 'vue-router'
import { setUnauthorizedHandler } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

/**
 * 创建带守卫的路由实例（独立函数便于测试，可注入自定义 history）。
 *
 * @param history: 路由历史模式，默认浏览器 history
 * @returns 已挂载全局守卫的 router 实例
 */
export function createAppRouter(history: RouterHistory = createWebHistory()): Router {
  const router = createRouter({
    history,
    routes: [
      { path: '/login', name: 'login', component: () => import('@/views/Login.vue') },
      { path: '/register', name: 'register', component: () => import('@/views/Register.vue') },
      {
        path: '/',
        component: () => import('@/views/Layout.vue'),
        children: [
          { path: '', redirect: '/overview' },
          { path: 'overview', name: 'overview', component: () => import('@/views/BabyOverview.vue') },
          { path: 'growth', name: 'growth', component: () => import('@/views/GrowthRecords.vue') },
          { path: 'diet', name: 'diet', component: () => import('@/views/DietRecords.vue') },
          { path: 'recipes', name: 'recipes', component: () => import('@/views/Recipes.vue') },
          { path: 'advisor', name: 'advisor', component: () => import('@/views/Advisor.vue') },
          {
            path: 'notifications',
            name: 'notifications',
            component: () => import('@/views/Notifications.vue')
          }
        ]
      },
      // 兜底：未匹配路由重定向首页
      { path: '/:pathMatch(.*)*', redirect: '/overview' }
    ]
  })

  // 全局前置守卫：公开页之外均要求已登录
  router.beforeEach((to) => {
    const auth = useAuthStore()
    const isPublic = to.name === 'login' || to.name === 'register'
    if (!isPublic && !auth.isLoggedIn) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    // 已登录访问登录/注册页时直接进入概览
    if (isPublic && auth.isLoggedIn) {
      return { path: '/overview' }
    }
    return true
  })

  // 注入 40100 处理：清 token 后跳转登录页（携带回跳地址）
  setUnauthorizedHandler(() => {
    const auth = useAuthStore()
    auth.logout()
    const current = router.currentRoute.value
    if (current.name !== 'login') {
      router.push({ name: 'login', query: { redirect: current.fullPath } })
    }
  })

  return router
}

// 默认导出单例路由，供 main.ts 挂载
const router = createAppRouter()
export default router
