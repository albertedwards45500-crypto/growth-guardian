/**
 * @file: src/api/recipes.ts
 * @description: 辅食推荐接口：食谱筛选、收藏、智能推荐与一周辅食计划。
 */

import { del, get, post, put } from './client'
import type {
  MealPlanItem,
  MealPlanItemPayload,
  PageResult,
  Recipe,
  RecipeFavorite
} from '@/types/api'

/**
 * 分页查询食谱，支持月龄/食材/营养标签/关键词多维筛选。
 *
 * @param params: age_months 月龄、ingredient 食材、nutrition 营养标签、keyword 名称、page、page_size
 * @returns 分页食谱结果
 * @throws Error 未认证（40100）时抛出
 */
export function listRecipes(
  params: {
    age_months?: number
    ingredient?: string
    nutrition?: string
    keyword?: string
    page?: number
    page_size?: number
  } = {}
): Promise<PageResult<Recipe>> {
  return get<PageResult<Recipe>>('/recipes', params)
}

/**
 * 获取当前用户收藏的食谱列表。
 *
 * @returns 收藏概要列表
 * @throws Error 未认证时抛出
 */
export function listFavorites(): Promise<RecipeFavorite[]> {
  return get<RecipeFavorite[]>('/recipes/favorites')
}

/**
 * 获取食谱详情。
 *
 * @param recipeId: 食谱 ID
 * @returns 食谱详情
 * @throws Error 食谱不存在（40400）时抛出
 */
export function getRecipe(recipeId: number): Promise<Recipe> {
  return get<Recipe>(`/recipes/${recipeId}`)
}

/**
 * 收藏食谱（幂等）。
 *
 * @param recipeId: 食谱 ID
 * @returns 收藏结果
 * @throws Error 食谱不存在时抛出
 */
export function favoriteRecipe(recipeId: number): Promise<{ favorited: boolean }> {
  return post<{ favorited: boolean }>(`/recipes/${recipeId}/favorite`)
}

/**
 * 取消收藏食谱（幂等）。
 *
 * @param recipeId: 食谱 ID
 * @returns 收藏结果
 */
export function unfavoriteRecipe(recipeId: number): Promise<{ favorited: boolean }> {
  return del<{ favorited: boolean }>(`/recipes/${recipeId}/favorite`)
}

/**
 * 根据宝宝月龄与过敏史智能推荐食谱（自动规避过敏食材）。
 *
 * @param babyId: 宝宝 ID
 * @param params: nutrition 营养标签筛选、page、page_size
 * @returns 分页推荐结果
 * @throws Error 档案不存在（40400）时抛出
 */
export function getRecommendations(
  babyId: number,
  params: { nutrition?: string; page?: number; page_size?: number } = {}
): Promise<PageResult<Recipe>> {
  return get<PageResult<Recipe>>(`/babies/${babyId}/recipes/recommendations`, params)
}

/**
 * 获取宝宝某一周的辅食计划。
 *
 * @param babyId: 宝宝 ID
 * @param weekStart: 周起始日期（周一，YYYY-MM-DD）
 * @returns 计划项列表
 * @throws Error 档案不存在时抛出
 */
export function getMealPlans(babyId: number, weekStart: string): Promise<MealPlanItem[]> {
  return get<MealPlanItem[]>(`/babies/${babyId}/meal-plans`, { week_start: weekStart })
}

/**
 * 整体覆盖保存某一周的辅食计划。
 *
 * @param babyId: 宝宝 ID
 * @param weekStart: 周起始日期（周一）
 * @param items: 计划项列表
 * @returns 保存后的计划项列表
 * @throws Error 计划项冲突（50000）时抛出
 */
export function saveMealPlans(
  babyId: number,
  weekStart: string,
  items: MealPlanItemPayload[]
): Promise<MealPlanItem[]> {
  return put<MealPlanItem[]>(`/babies/${babyId}/meal-plans`, { week_start: weekStart, items })
}
