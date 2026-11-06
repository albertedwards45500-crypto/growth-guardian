/**
 * @file: tests/client.spec.ts
 * @description: API 客户端测试：统一响应解包、40100 登出、业务错误拒绝与 HTTP 错误拒绝。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import {
  CODE_UNAUTHORIZED,
  TOKEN_KEY,
  clearToken,
  getToken,
  http,
  setUnauthorizedHandler
} from '@/api/client'

/**
 * 构造最小 AxiosResponse 对象。
 *
 * @param status: HTTP 状态码
 * @param data: 响应体
 * @returns AxiosResponse 结构
 */
function makeResponse(status: number, data: unknown): AxiosResponse {
  return {
    data,
    status,
    statusText: 'OK',
    headers: {},
    config: {} as InternalAxiosRequestConfig
  } as AxiosResponse
}

/**
 * 注入一次性 mock adapter（走完整拦截器链）。
 *
 * @param status: HTTP 状态码
 * @param body: 响应体
 */
function mockAdapter(status: number, body: unknown): void {
  http.defaults.adapter = async (config) => makeResponse(status, body) // config 供 axios 校验
}

describe('api client 响应拦截器', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('code=0 时解包返回 data', async () => {
    mockAdapter(200, { code: 0, message: 'ok', data: { hello: 'world' } })
    const result = (await http.get('/demo')) as unknown as { hello: string }
    expect(result).toEqual({ hello: 'world' })
  })

  it('code=40100 时清除 token 并触发未认证回调', async () => {
    localStorage.setItem(TOKEN_KEY, 'fake-token')
    expect(getToken()).toBe('fake-token')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    mockAdapter(200, { code: CODE_UNAUTHORIZED, message: '登录已失效', data: null })

    await expect(http.get('/demo')).rejects.toThrow('登录已失效')
    expect(getToken()).toBeNull()
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('code=42200 时以 message 拒绝', async () => {
    mockAdapter(200, { code: 42200, message: '参数校验失败', data: null })
    await expect(http.get('/demo')).rejects.toThrow('参数校验失败')
  })

  it('code=40300 等其他业务码同样以 message 拒绝', async () => {
    mockAdapter(200, { code: 40900, message: '该食材已在过敏清单中', data: null })
    await expect(http.post('/demo')).rejects.toThrow('该食材已在过敏清单中')
  })

  it('HTTP 500 时拒绝并提示状态', async () => {
    mockAdapter(500, { code: 50000, message: '服务器开小差了', data: null })
    await expect(http.get('/demo')).rejects.toThrow('服务器开小差了')
  })

  it('clearToken 移除本地令牌', () => {
    localStorage.setItem(TOKEN_KEY, 'abc')
    clearToken()
    expect(getToken()).toBeNull()
  })
})
