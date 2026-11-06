/**
 * @file: src/api/client.ts
 * @description: Axios 客户端封装：Bearer 注入、统一响应解包、40100 登出跳转与错误拒绝。
 */

import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse
} from 'axios'
import type { ApiEnvelope } from '@/types/api'

/** localStorage 中保存访问令牌的键名 */
export const TOKEN_KEY = 'czb_token'

/** 未认证业务码（令牌缺失/失效） */
export const CODE_UNAUTHORIZED = 40100

/** 无权限业务码 */
export const CODE_FORBIDDEN = 40300

/** 登录限流业务码 */
export const CODE_RATE_LIMITED = 42900

/** 未认证时的回调处理器类型 */
export type UnauthorizedHandler = () => void

/** 未认证处理器：默认回退为整页跳转登录页 */
let unauthorizedHandler: UnauthorizedHandler = () => {
  if (!window.location.pathname.startsWith('/login')) {
    window.location.assign('/login')
  }
}

/**
 * 注册未认证（40100）时的处理回调（由路由层注入 router.push 逻辑）。
 *
 * @param handler: 未认证回调函数
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler
}

/**
 * 读取本地保存的访问令牌。
 *
 * @returns 令牌字符串，未登录时为 null
 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

/**
 * 保存访问令牌到本地。
 *
 * @param token: JWT 访问令牌
 */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

/**
 * 清除本地令牌（登出）。
 */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * 创建带拦截器的 axios 实例。
 *
 * @returns 配置完成的 axios 实例
 */
function createHttp(): AxiosInstance {
  const instance = axios.create({
    // 后端统一前缀 /api/v1，开发环境由 vite 代理转发
    baseURL: '/api/v1',
    timeout: 15000
  })

  // 请求拦截器：注入 Bearer 令牌
  instance.interceptors.request.use((config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // 响应拦截器：解包统一响应结构
  instance.interceptors.response.use(
    (response: AxiosResponse<ApiEnvelope>) => {
      const body = response.data
      // 后端契约：HTTP 200 + {code, message, data}
      if (body && typeof body === 'object' && 'code' in body) {
        // 业务成功：直接返回 data
        if (body.code === 0) {
          return body.data as never
        }
        // 令牌失效：清 token 并跳转登录页
        if (body.code === CODE_UNAUTHORIZED) {
          clearToken()
          unauthorizedHandler()
          return Promise.reject(new Error(body.message || '登录已失效，请重新登录'))
        }
        // 其余业务错误：拒绝并携带提示信息
        return Promise.reject(new Error(body.message || `请求失败（${body.code}）`))
      }
      // 非统一结构（异常兜底）：原样返回
      return response.data as never
    },
    (error: AxiosError) => {
      // HTTP 层错误：提取服务端 message 或状态码提示
      let message = '网络请求失败，请稍后重试'
      if (error.response) {
        const data = error.response.data as Partial<ApiEnvelope> | undefined
        message = data?.message || `请求失败（HTTP ${error.response.status}）`
      } else if (error.code === 'ECONNABORTED') {
        message = '请求超时，请稍后重试'
      }
      return Promise.reject(new Error(message))
    }
  )

  return instance
}

/** 全局共享的 axios 实例 */
export const http = createHttp()

/**
 * 通用 GET 请求：返回解包后的业务数据。
 *
 * @param url: 相对 baseURL 的路径
 * @param params: 查询参数
 * @returns 业务数据
 * @throws Error 业务失败或网络错误时抛出
 */
export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  return http.get(url, { params } as AxiosRequestConfig) as unknown as Promise<T>
}

/**
 * 通用 POST 请求：返回解包后的业务数据。
 *
 * @param url: 相对 baseURL 的路径
 * @param body: 请求体
 * @returns 业务数据
 * @throws Error 业务失败或网络错误时抛出
 */
export async function post<T>(url: string, body?: unknown): Promise<T> {
  return http.post(url, body) as unknown as Promise<T>
}

/**
 * 通用 PUT 请求：返回解包后的业务数据。
 *
 * @param url: 相对 baseURL 的路径
 * @param body: 请求体
 * @returns 业务数据
 * @throws Error 业务失败或网络错误时抛出
 */
export async function put<T>(url: string, body?: unknown): Promise<T> {
  return http.put(url, body) as unknown as Promise<T>
}

/**
 * 通用 PATCH 请求：返回解包后的业务数据。
 *
 * @param url: 相对 baseURL 的路径
 * @param body: 请求体
 * @returns 业务数据
 * @throws Error 业务失败或网络错误时抛出
 */
export async function patch<T>(url: string, body?: unknown): Promise<T> {
  return http.patch(url, body) as unknown as Promise<T>
}

/**
 * 通用 DELETE 请求：返回解包后的业务数据。
 *
 * @param url: 相对 baseURL 的路径
 * @returns 业务数据
 * @throws Error 业务失败或网络错误时抛出
 */
export async function del<T>(url: string): Promise<T> {
  return http.delete(url) as unknown as Promise<T>
}
