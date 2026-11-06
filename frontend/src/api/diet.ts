/**
 * @file: src/api/diet.ts
 * @description: 饮食管理接口：饮食记录、营养分析与过敏食材。
 */

import { del, get, post, put } from './client'
import type {
  Allergy,
  AllergyPayload,
  DietRecord,
  DietRecordPayload,
  NutritionSummary,
  PageResult
} from '@/types/api'

/**
 * 新增饮食记录（母乳/配方奶/辅食）。
 *
 * @param babyId: 宝宝 ID
 * @param payload: 记录数据（details 需与 record_type 匹配）
 * @returns 新建的饮食记录
 * @throws Error 明细与类型不匹配（40002）时抛出
 */
export function createDietRecord(
  babyId: number,
  payload: DietRecordPayload
): Promise<DietRecord> {
  return post<DietRecord>(`/babies/${babyId}/diet-records`, payload)
}

/**
 * 分页查询饮食记录，支持按日期过滤。
 *
 * @param babyId: 宝宝 ID
 * @param params: record_date 过滤日期（YYYY-MM-DD）、page 页码、page_size 条数
 * @returns 分页结果
 * @throws Error 档案不存在时抛出
 */
export function listDietRecords(
  babyId: number,
  params: { record_date?: string; page?: number; page_size?: number } = {}
): Promise<PageResult<DietRecord>> {
  return get<PageResult<DietRecord>>(`/babies/${babyId}/diet-records`, params)
}

/**
 * 更新饮食记录（字段均可选）。
 *
 * @param recordId: 记录 ID
 * @param payload: 更新字段
 * @returns 更新后的饮食记录
 * @throws Error 记录不存在（40400）时抛出
 */
export function updateDietRecord(
  recordId: number,
  payload: Partial<DietRecordPayload>
): Promise<DietRecord> {
  return put<DietRecord>(`/diet-records/${recordId}`, payload)
}

/**
 * 删除饮食记录。
 *
 * @param recordId: 记录 ID
 * @returns 删除结果
 * @throws Error 记录不存在（40400）时抛出
 */
export function deleteDietRecord(recordId: number): Promise<{ deleted: boolean }> {
  return del<{ deleted: boolean }>(`/diet-records/${recordId}`)
}

/**
 * 获取指定日期的营养分析摘要。
 *
 * @param babyId: 宝宝 ID
 * @param targetDate: 分析日期（YYYY-MM-DD，必填）
 * @returns 营养分析摘要
 * @throws Error 档案不存在时抛出
 */
export function getDietAnalysis(babyId: number, targetDate: string): Promise<NutritionSummary> {
  return get<NutritionSummary>(`/babies/${babyId}/diet-analysis`, { target_date: targetDate })
}

/**
 * 获取过敏食材列表。
 *
 * @param babyId: 宝宝 ID
 * @returns 过敏食材列表
 * @throws Error 档案不存在时抛出
 */
export function listAllergies(babyId: number): Promise<Allergy[]> {
  return get<Allergy[]>(`/babies/${babyId}/allergies`)
}

/**
 * 新增过敏食材（重复添加返回 40900 冲突）。
 *
 * @param babyId: 宝宝 ID
 * @param payload: 食材与严重程度
 * @returns 新建的过敏记录
 * @throws Error 食材已存在（40900）时抛出
 */
export function createAllergy(babyId: number, payload: AllergyPayload): Promise<Allergy> {
  return post<Allergy>(`/babies/${babyId}/allergies`, payload)
}

/**
 * 删除过敏食材记录。
 *
 * @param allergyId: 过敏记录 ID
 * @returns 删除结果
 * @throws Error 记录不存在（40400）时抛出
 */
export function deleteAllergy(allergyId: number): Promise<{ deleted: boolean }> {
  return del<{ deleted: boolean }>(`/allergies/${allergyId}`)
}
