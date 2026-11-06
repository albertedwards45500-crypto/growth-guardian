/**
 * @file: src/api/babies.ts
 * @description: 宝宝档案接口：增删改查与成长印记聚合。
 */

import { del, get, post, put } from './client'
import type { Baby, BabyPayload, GrowthSummary } from '@/types/api'

/**
 * 获取当前用户全部宝宝档案。
 *
 * @returns 宝宝档案列表
 * @throws Error 未认证时抛出
 */
export function listBabies(): Promise<Baby[]> {
  return get<Baby[]>('/babies')
}

/**
 * 创建宝宝档案（首个档案自动设为默认）。
 *
 * @param payload: 宝宝信息
 * @returns 新建的宝宝档案
 * @throws Error 参数校验失败（42200）时抛出
 */
export function createBaby(payload: BabyPayload): Promise<Baby> {
  return post<Baby>('/babies', payload)
}

/**
 * 更新宝宝档案（字段均可选）。
 *
 * @param babyId: 宝宝 ID
 * @param payload: 更新字段
 * @returns 更新后的宝宝档案
 * @throws Error 档案不存在（40400）时抛出
 */
export function updateBaby(babyId: number, payload: BabyPayload): Promise<Baby> {
  return put<Baby>(`/babies/${babyId}`, payload)
}

/**
 * 删除宝宝档案（级联删除其记录）。
 *
 * @param babyId: 宝宝 ID
 * @returns 删除结果
 * @throws Error 档案不存在（40400）时抛出
 */
export function deleteBaby(babyId: number): Promise<{ deleted: boolean }> {
  return del<{ deleted: boolean }>(`/babies/${babyId}`)
}

/**
 * 获取成长印记聚合数据（月龄/阶段/最近测量/里程碑进度）。
 *
 * @param babyId: 宝宝 ID
 * @returns 成长印记数据
 * @throws Error 档案不存在（40400）时抛出
 */
export function getBabySummary(babyId: number): Promise<GrowthSummary> {
  return get<GrowthSummary>(`/babies/${babyId}/summary`)
}
