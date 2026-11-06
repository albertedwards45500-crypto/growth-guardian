/**
 * @file: tests/Login.spec.ts
 * @description: 登录页测试：非法提交被前端校验拦截、合法提交调用登录接口。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { mount } from '@vue/test-utils'
import Login from '@/views/Login.vue'
import { useAuthStore } from '@/stores/auth'

// Mock 认证与用户接口模块（登录后 store 会拉取用户资料）
vi.mock('@/api/auth', () => ({
  register: vi.fn(),
  login: vi.fn()
}))

vi.mock('@/api/users', () => ({
  getMe: vi.fn().mockResolvedValue({
    id: 1,
    phone: '13800000000',
    nickname: '家长',
    avatar_url: null,
    created_at: '2026-01-01T00:00:00'
  }),
  updateMe: vi.fn()
}))

import { login as loginApi } from '@/api/auth'

/**
 * 创建挂载测试所需的 pinia 与 router。
 *
 * @returns 应用插件数组
 */
function makePlugins(): [ReturnType<typeof createPinia>, ReturnType<typeof createRouter>] {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: Login },
      { path: '/overview', component: { template: '<div />' } }
    ]
  })
  return [pinia, router]
}

describe('Login.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('非法手机号提交被校验拦截，不调用登录接口', async () => {
    const [pinia, router] = makePlugins()
    const wrapper = mount(Login, { global: { plugins: [pinia, router] } })

    await wrapper.find('input#phone').setValue('12345')
    await wrapper.find('input#password').setValue('123456')
    await wrapper.find('form').trigger('submit')
    await vi.waitFor(() => {
      expect(wrapper.find('.form-error').text()).toContain('11 位')
    })

    expect(loginApi).not.toHaveBeenCalled()
  })

  it('密码不足 6 位被校验拦截', async () => {
    const [pinia, router] = makePlugins()
    const wrapper = mount(Login, { global: { plugins: [pinia, router] } })

    await wrapper.find('input#phone').setValue('13800000000')
    await wrapper.find('input#password').setValue('123')
    await wrapper.find('form').trigger('submit')
    await vi.waitFor(() => {
      expect(wrapper.find('.form-error').text()).toContain('至少 6 位')
    })

    expect(loginApi).not.toHaveBeenCalled()
  })

  it('合法提交调用登录接口并写入 token', async () => {
    const [pinia, router] = makePlugins()
    ;(loginApi as ReturnType<typeof vi.fn>).mockResolvedValue({
      access_token: 'jwt-token',
      token_type: 'bearer',
      expires_in: 7200
    })
    const wrapper = mount(Login, { global: { plugins: [pinia, router] } })

    await wrapper.find('input#phone').setValue('13800000000')
    await wrapper.find('input#password').setValue('123456')
    await wrapper.find('form').trigger('submit')

    await vi.waitFor(() => {
      expect(loginApi).toHaveBeenCalledTimes(1)
    })
    expect(loginApi).toHaveBeenCalledWith('13800000000', '123456')
    expect(useAuthStore().token).toBe('jwt-token')
    // 等待登录成功后的异步跳转完成
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe('/overview')
    })
  })

  it('接口报错时展示错误信息', async () => {
    const [pinia, router] = makePlugins()
    ;(loginApi as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('手机号或密码错误'))
    const wrapper = mount(Login, { global: { plugins: [pinia, router] } })

    await wrapper.find('input#phone').setValue('13800000000')
    await wrapper.find('input#password').setValue('123456')
    await wrapper.find('form').trigger('submit')

    await vi.waitFor(() => {
      expect(wrapper.find('.form-error').text()).toContain('手机号或密码错误')
    })
  })
})
