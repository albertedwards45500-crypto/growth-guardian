/**
 * @file: src/api/users.ts
 * @description: 用户资料接口：查询与更新当前用户信息。
 */

import { get, put } from './client'
import type { UserProfile } from '@/types/api'

/**
 * 获取当前登录用户资料。
 *
 * @returns 用户资料
 * @throws Error 未认证（40100）时抛出
 */
export function getMe(): Promise<UserProfile> {
  return get<UserProfile>('/users/me')
}

/**
 * 更新当前用户昵称与头像。
 *
 * @param payload: 更新字段（nickname / avatar_url 可选）
 * @returns 更新后的用户资料
 * @throws Error 业务错误时抛出
 */
export function updateMe(payload: {
  nickname?: string
  avatar_url?: string
}): Promise<UserProfile> {
  return put<UserProfile>('/users/me', payload)
}
