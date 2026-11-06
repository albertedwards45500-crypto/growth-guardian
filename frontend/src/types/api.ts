/**
 * @file: src/types/api.ts
 * @description: 与后端 schema 对齐的全局类型定义（字段名以 backend/app/schemas 为准）。
 */

/** 统一响应包装（后端 ApiResponse） */
export interface ApiEnvelope<T = unknown> {
  /** 业务码，0 表示成功 */
  code: number
  /** 提示信息 */
  message: string
  /** 业务数据 */
  data: T
}

/** 分页结果（后端 PageResult） */
export interface PageResult<T> {
  /** 当前页数据 */
  items: T[]
  /** 总条数 */
  total: number
  /** 当前页码（从 1 开始） */
  page: number
  /** 每页条数 */
  page_size: number
}

/** 登录令牌响应（TokenResponse） */
export interface TokenResponse {
  /** JWT 访问令牌 */
  access_token: string
  /** 令牌类型 */
  token_type: string
  /** 有效期（秒） */
  expires_in: number
}

/** 用户资料（UserProfile） */
export interface UserProfile {
  id: number
  phone: string
  nickname: string
  avatar_url: string | null
  created_at: string
}

/** 宝宝性别类型 */
export type Gender = 'male' | 'female'

/** 宝宝档案（BabyResponse） */
export interface Baby {
  id: number
  name: string
  gender: Gender | null
  birth_date: string
  avatar_url: string | null
  is_default: boolean
  created_at: string
}

/** 创建/更新宝宝档案的载荷 */
export interface BabyPayload {
  /** 宝宝昵称 */
  name?: string
  /** 性别 male/female */
  gender?: Gender | null
  /** 出生日期 YYYY-MM-DD */
  birth_date?: string
  /** 头像地址 */
  avatar_url?: string | null
  /** 是否默认档案 */
  is_default?: boolean
}

/** 成长印记聚合（GrowthSummary） */
export interface GrowthSummary {
  baby_id: number
  baby_name: string
  /** 满月龄 */
  age_months: number
  /** 天数 */
  age_days: number
  /** 阶段名称 */
  stage_name: string
  latest_weight_kg: number | null
  latest_height_cm: number | null
  latest_head_circumference_cm: number | null
  latest_measure_date: string | null
  /** 阶段里程碑完成数 */
  milestone_progress: Record<string, number>
}

/** 生长记录（GrowthRecordResponse） */
export interface GrowthRecord {
  id: number
  baby_id: number
  record_date: string
  weight_kg: number | null
  height_cm: number | null
  head_circumference_cm: number | null
  note: string | null
  created_at: string
}

/** 新增生长记录载荷 */
export interface GrowthRecordPayload {
  /** 测量日期 YYYY-MM-DD */
  record_date: string
  /** 体重(kg) */
  weight_kg?: number | null
  /** 身高(cm) */
  height_cm?: number | null
  /** 头围(cm) */
  head_circumference_cm?: number | null
  /** 备注 */
  note?: string | null
}

/** 里程碑（MilestoneResponse） */
export interface Milestone {
  id: number
  baby_id: number
  milestone_type: string
  name: string
  achieved_at: string
  note: string | null
  created_at: string
}

/** 新增里程碑载荷 */
export interface MilestonePayload {
  /** 里程碑类型编码 */
  milestone_type: string
  /** 名称 */
  name: string
  /** 达成日期 YYYY-MM-DD */
  achieved_at: string
  /** 备注 */
  note?: string | null
}

/** WHO 参考线单点（WhoReferencePoint） */
export interface WhoReferencePoint {
  /** 月龄 */
  month: number
  p3: number
  p15: number
  p50: number
  p85: number
  p97: number
}

/** WHO 2006 参考线（WhoReference） */
export interface WhoReference {
  /** 身长(cm)分位线 */
  height: WhoReferencePoint[]
  /** 体重(kg)分位线 */
  weight: WhoReferencePoint[]
}

/** 生长曲线数据点（CurvePoint） */
export interface CurvePoint {
  record_date: string
  /** 月龄（浮点） */
  age_months: number
  weight_kg: number | null
  height_cm: number | null
  head_circumference_cm: number | null
}

/** 生长曲线响应（GrowthCurveResponse） */
export interface GrowthCurve {
  baby_id: number
  weight_series: CurvePoint[]
  height_series: CurvePoint[]
  head_circumference_series: CurvePoint[]
  /** 0-24 月龄宝宝返回分位数据，超龄为 null */
  who_reference: WhoReference | null
}

/** 饮食记录类型 */
export type DietType = 'breast_milk' | 'formula' | 'solid_food'

/** 饮食记录（DietRecordResponse） */
export interface DietRecord {
  id: number
  baby_id: number
  record_date: string
  record_type: DietType
  /** 类型化明细：母乳 {left_minutes,right_minutes}、配方奶 {amount_ml}、辅食 {food_items:[]} */
  details: Record<string, unknown> | null
  note: string | null
  created_at: string
}

/** 新增/更新饮食记录载荷 */
export interface DietRecordPayload {
  /** 记录日期 YYYY-MM-DD */
  record_date: string
  /** 记录类型 */
  record_type: DietType
  /** 类型化明细 */
  details?: Record<string, unknown> | null
  /** 备注 */
  note?: string | null
}

/** 营养分析摘要（NutritionSummary） */
export interface NutritionSummary {
  baby_id: number
  date: string
  /** 喂养次数 */
  feed_count: number
  /** 母乳总时长（分钟） */
  breast_milk_minutes: number
  /** 配方奶总量（ml） */
  formula_amount_ml: number
  /** 辅食次数 */
  solid_food_count: number
  /** 当日辅食食材清单 */
  food_names: string[]
}

/** 过敏严重程度 */
export type AllergySeverity = 'mild' | 'moderate' | 'severe'

/** 过敏食材（AllergyResponse） */
export interface Allergy {
  id: number
  baby_id: number
  ingredient: string
  severity: AllergySeverity | null
  note: string | null
  created_at: string
}

/** 新增过敏食材载荷 */
export interface AllergyPayload {
  /** 食材名称 */
  ingredient: string
  /** 严重程度 mild/moderate/severe */
  severity?: AllergySeverity | null
  /** 备注 */
  note?: string | null
}

/** 食谱食材条目（后端为自由结构，字符串或对象） */
export type RecipeIngredient = string | Record<string, unknown>

/** 食谱（RecipeResponse） */
export interface Recipe {
  id: number
  title: string
  cover_url: string | null
  suitable_age_min: number
  suitable_age_max: number
  ingredients: RecipeIngredient[]
  steps: string[]
  nutrition_tags: string[]
  tips: string | null
  /** 当前用户是否已收藏 */
  is_favorite: boolean
  created_at: string
}

/** 食谱收藏概要（RecipeFavoriteResponse） */
export interface RecipeFavorite {
  id: number
  recipe_id: number
  recipe_title: string
  cover_url: string | null
  created_at: string
}

/** 餐次类型 */
export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack'

/** 辅食计划项（MealPlanItemResponse） */
export interface MealPlanItem {
  id: number
  /** 星期（0=周一） */
  day_of_week: number
  meal_type: MealType
  recipe_id: number | null
  recipe_title: string | null
  note: string | null
}

/** 辅食计划写入项（MealPlanItemRequest） */
export interface MealPlanItemPayload {
  /** 星期（0=周一） */
  day_of_week: number
  /** 餐次类型 */
  meal_type: MealType
  /** 食谱 ID，可空表示待定 */
  recipe_id?: number | null
  /** 备注 */
  note?: string | null
}

/** 喂养指南（GuideResponse） */
export interface Guide {
  id: number
  month_start: number
  month_end: number
  title: string
  content: string
  food_suggestions: string[]
}

/** 常见问题（FaqResponse） */
export interface Faq {
  id: number
  category: string
  question: string
  answer: string
}

/** 通知（NotificationResponse） */
export interface Notification {
  id: number
  notify_type: string
  title: string
  content: string
  is_read: boolean
  created_at: string
}
