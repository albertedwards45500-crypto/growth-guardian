/**
 * @file: src/api/auth.ts
 * @description: 认证接口：注册与登录。
 */

import { post } from './client'
import type { TokenResponse, UserProfile } from '@/types/api'

/**
 * 用户注册。
 *
 * @param phone: 手机号（11 位）
 * @param password: 密码（至少 6 位）
 * @param nickname: 昵称（可选）
 * @returns 新用户资料
 * @throws Error 手机号已注册（40900）等业务错误
 */
export function register(phone: string, password: string, nickname?: string): Promise<UserProfile> {
  return post<UserProfile>('/auth/register', { phone, password, nickname })
}

/**
 * 手机号密码登录。
 *
 * @param phone: 手机号
 * @param password: 密码
 * @returns 令牌响应（access_token / expires_in）
 * @throws Error 密码错误（40100）或登录限流（42900）
 */
export function login(phone: string, password: string): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/login', { phone, password })
}
