/**
 * @file: src/api/growth.ts
 * @description: 成长记录接口：生长记录、生长曲线与里程碑。
 */

import { del, get, post } from './client'
import type {
  GrowthCurve,
  GrowthRecord,
  GrowthRecordPayload,
  Milestone,
  MilestonePayload
} from '@/types/api'

/**
 * 新增生长测量记录（体重/身高/头围至少一项）。
 *
 * @param babyId: 宝宝 ID
 * @param payload: 测量数据
 * @returns 新建的生长记录
 * @throws Error 三项均未填写（40001）或校验失败时抛出
 */
export function createGrowthRecord(
  babyId: number,
  payload: GrowthRecordPayload
): Promise<GrowthRecord> {
  return post<GrowthRecord>(`/babies/${babyId}/growth-records`, payload)
}

/**
 * 获取生长记录列表（按测量日期倒序）。
 *
 * @param babyId: 宝宝 ID
 * @returns 生长记录列表
 * @throws Error 档案不存在时抛出
 */
export function listGrowthRecords(babyId: number): Promise<GrowthRecord[]> {
  return get<GrowthRecord[]>(`/babies/${babyId}/growth-records`)
}

/**
 * 获取生长曲线数据（含 WHO 0-24 月参考线，超龄为 null）。
 *
 * @param babyId: 宝宝 ID
 * @returns 曲线数据
 * @throws Error 档案不存在时抛出
 */
export function getGrowthCurve(babyId: number): Promise<GrowthCurve> {
  return get<GrowthCurve>(`/babies/${babyId}/growth-curve`)
}

/**
 * 删除生长记录。
 *
 * @param recordId: 记录 ID
 * @returns 删除结果
 * @throws Error 记录不存在（40400）时抛出
 */
export function deleteGrowthRecord(recordId: number): Promise<{ deleted: boolean }> {
  return del<{ deleted: boolean }>(`/growth-records/${recordId}`)
}

/**
 * 获取里程碑列表（按达成日期倒序）。
 *
 * @param babyId: 宝宝 ID
 * @returns 里程碑列表
 * @throws Error 档案不存在时抛出
 */
export function listMilestones(babyId: number): Promise<Milestone[]> {
  return get<Milestone[]>(`/babies/${babyId}/milestones`)
}

/**
 * 新增里程碑。
 *
 * @param babyId: 宝宝 ID
 * @param payload: 里程碑数据
 * @returns 新建的里程碑
 * @throws Error 校验失败（42200）时抛出
 */
export function createMilestone(babyId: number, payload: MilestonePayload): Promise<Milestone> {
  return post<Milestone>(`/babies/${babyId}/milestones`, payload)
}

/**
 * 删除里程碑。
 *
 * @param milestoneId: 里程碑 ID
 * @returns 删除结果
 * @throws Error 记录不存在（40400）时抛出
 */
export function deleteMilestone(milestoneId: number): Promise<{ deleted: boolean }> {
  return del<{ deleted: boolean }>(`/milestones/${milestoneId}`)
}
