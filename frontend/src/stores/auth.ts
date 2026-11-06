/**
 * @file: src/stores/auth.ts
 * @description: 认证状态 store：令牌管理、登录/登出与当前用户资料。
 */

import { defineStore } from 'pinia'
import { clearToken, getToken, setToken } from '@/api/client'
import * as authApi from '@/api/auth'
import { getMe } from '@/api/users'
import { useBabyStore } from '@/stores/baby'
import type { UserProfile } from '@/types/api'

/** 认证 store 的状态结构 */
interface AuthState {
  /** JWT 访问令牌 */
  token: string | null
  /** 当前用户资料 */
  user: UserProfile | null
}

/**
 * 认证状态 store：负责令牌持久化与用户资料加载。
 */
export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: getToken(),
    user: null
  }),
  getters: {
    /**
     * 是否已登录（持有令牌）。
     *
     * @param state: store 状态
     * @returns 已登录返回 true
     */
    isLoggedIn: (state): boolean => Boolean(state.token)
  },
  actions: {
    /**
     * 手机号密码登录：保存令牌并拉取用户资料。
     *
     * @param phone: 手机号
     * @param password: 密码
     * @throws Error 登录失败（密码错误/限流）时抛出
     */
    async login(phone: string, password: string): Promise<void> {
      const tokenResp = await authApi.login(phone, password)
      setToken(tokenResp.access_token)
      this.token = tokenResp.access_token
      await this.fetchUser()
    },
    /**
     * 拉取当前用户资料。
     *
     * @throws Error 未认证时抛出
     */
    async fetchUser(): Promise<void> {
      this.user = await getMe()
    },
    /**
     * 注册新用户（不自动登录）。
     *
     * @param phone: 手机号
     * @param password: 密码
     * @param nickname: 昵称（可选）
     * @throws Error 手机号已注册时抛出
     */
    async register(phone: string, password: string, nickname?: string): Promise<void> {
      await authApi.register(phone, password, nickname)
    },
    /**
     * 登出：清除令牌与用户资料，并失效宝宝列表缓存。
     */
    logout(): void {
      clearToken()
      this.token = null
      this.user = null
      // 换账号后需重新拉取宝宝列表，避免读到上一个账号的缓存
      useBabyStore().invalidate()
    }
  }
})
