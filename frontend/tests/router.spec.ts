/**
 * @file: tests/router.spec.ts
 * @description: 路由守卫测试：无令牌访问受保护路由重定向登录页，已登录访问登录页跳转概览。
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from '@/router'

describe('路由守卫', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it.each(['/overview', '/advisor'])('无 token 访问 %s 时重定向 /login 并携带回跳地址', async (path) => {
    const router = createAppRouter(createMemoryHistory())
    await router.push(path)
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe(path)
  })

  it('无 token 访问登录页可正常进入', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('已登录访问登录页时重定向 /overview', async () => {
    localStorage.setItem('czb_token', 'jwt-token')
    const router = createAppRouter(createMemoryHistory())
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('overview')
  })

  it('已登录可进入受保护路由', async () => {
    localStorage.setItem('czb_token', 'jwt-token')
    const router = createAppRouter(createMemoryHistory())
    await router.push('/notifications')
    expect(router.currentRoute.value.name).toBe('notifications')
  })

  it('已登录可进入成长顾问', async () => {
    localStorage.setItem('czb_token', 'jwt-token')
    const router = createAppRouter(createMemoryHistory())
    await router.push('/advisor')
    expect(router.currentRoute.value.name).toBe('advisor')
  })
})
