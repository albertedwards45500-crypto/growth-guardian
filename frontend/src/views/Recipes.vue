<script setup lang="ts">
/**
 * @file: src/views/Recipes.vue
 * @description: 食谱推荐页：全部食谱（多维筛选+分页）/ 收藏 / 智能推荐 / 一周辅食计划四个 Tab，
 *   附食谱详情弹层、收藏切换与 7 天×餐次计划编辑保存。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useBabyStore } from '@/stores/baby'
import {
  favoriteRecipe,
  getMealPlans,
  getRecipe,
  getRecommendations,
  listFavorites,
  listRecipes,
  saveMealPlans,
  unfavoriteRecipe
} from '@/api/recipes'
import type { MealPlanItem, MealType, Recipe, RecipeFavorite } from '@/types/api'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import AppModal from '@/components/AppModal.vue'

// 宝宝 store
const babyStore = useBabyStore()

// 页面状态
const loading = ref(false)
const error = ref('')

// 当前激活的 Tab
const activeTab = ref<'all' | 'favorites' | 'recommend' | 'plan'>('all')

// ---- 全部食谱筛选状态 ----
const filters = reactive<{ age_months: string; ingredient: string; nutrition: string; keyword: string }>({
  age_months: '',
  ingredient: '',
  nutrition: '',
  keyword: ''
})

// 列表数据（全部/推荐共用分页结构）
const recipes = ref<Recipe[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10

// 收藏列表
const favorites = ref<RecipeFavorite[]>([])

// 详情弹层
const detail = ref<Recipe | null>(null)
const detailLoading = ref(false)

// 详情内食材展示文案
const ingredientTexts = computed<string[]>(() => {
  if (!detail.value) return []
  return detail.value.ingredients.map((item) =>
    typeof item === 'string' ? item : String((item as Record<string, unknown>)['name'] ?? JSON.stringify(item))
  )
})

/** 总页数（至少 1 页） */
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ---- 一周计划状态 ----
// 餐次定义
const mealTypes: Array<{ value: MealType; label: string }> = [
  { value: 'breakfast', label: '早餐' },
  { value: 'lunch', label: '午餐' },
  { value: 'dinner', label: '晚餐' },
  { value: 'snack', label: '加餐' }
]
// 星期文案
const dayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

// 周起始日期（本周一）
function mondayOfThisWeek(): string {
  const now = new Date()
  const day = now.getDay() === 0 ? 7 : now.getDay()
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (day - 1))
  return monday.toISOString().slice(0, 10)
}

const weekStart = ref(mondayOfThisWeek())
// 计划草稿：key 为 `${day}-${mealType}`，value 为食谱 id（0 表示待定）
const planDraft = reactive<Record<string, { recipeId: number; note: string }>>({})
// 计划保存中标记
const planSaving = ref(false)
// 计划保存提示
const planMessage = ref('')

/**
 * 生成计划草稿的 key。
 *
 * @param day: 星期索引（0=周一）
 * @param meal: 餐次类型
 * @returns 草稿 key
 */
function planKey(day: number, meal: MealType): string {
  return `${day}-${meal}`
}

/**
 * 根据周起始日期计算某天日期。
 *
 * @param day: 星期索引（0=周一）
 * @returns 日期字符串
 */
function dateOfDay(day: number): string {
  const base = new Date(`${weekStart.value}T00:00:00`)
  base.setDate(base.getDate() + day)
  return base.toISOString().slice(0, 10)
}

/**
 * 加载当前 Tab 的数据。
 *
 * @throws Error 网络错误时展示错误态
 */
async function loadActiveTab(): Promise<void> {
  error.value = ''
  if (activeTab.value === 'favorites') {
    loading.value = true
    try {
      favorites.value = await listFavorites()
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载失败，请稍后重试'
    } finally {
      loading.value = false
    }
    return
  }
  if (activeTab.value === 'plan') {
    loading.value = true
    try {
      const babyId = babyStore.currentBabyId
      const items: MealPlanItem[] = babyId === null ? [] : await getMealPlans(babyId, weekStart.value)
      // 初始化草稿
      Object.keys(planDraft).forEach((k) => delete planDraft[k])
      for (let d = 0; d < 7; d++) {
        for (const meal of mealTypes) {
          planDraft[planKey(d, meal.value)] = { recipeId: 0, note: '' }
        }
      }
      for (const item of items) {
        const key = planKey(item.day_of_week, item.meal_type)
        if (planDraft[key]) {
          planDraft[key].recipeId = item.recipe_id ?? 0
          planDraft[key].note = item.note ?? ''
        }
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载失败，请稍后重试'
    } finally {
      loading.value = false
    }
    return
  }

  // 全部食谱 / 智能推荐（均为分页列表）
  loading.value = true
  try {
    if (activeTab.value === 'all') {
      const params: Record<string, unknown> = { page: page.value, page_size: pageSize }
      if (filters.age_months) params.age_months = Number(filters.age_months)
      if (filters.ingredient.trim()) params.ingredient = filters.ingredient.trim()
      if (filters.nutrition.trim()) params.nutrition = filters.nutrition.trim()
      if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
      const resp = await listRecipes(params)
      recipes.value = resp.items
      total.value = resp.total
    } else {
      const babyId = babyStore.currentBabyId
      if (babyId === null) {
        recipes.value = []
        total.value = 0
        return
      }
      const params: Record<string, unknown> = { page: page.value, page_size: pageSize }
      if (filters.nutrition.trim()) params.nutrition = filters.nutrition.trim()
      const resp = await getRecommendations(babyId, params)
      recipes.value = resp.items
      total.value = resp.total
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

/**
 * 应用筛选：回到第一页并加载。
 */
function applyFilters(): void {
  page.value = 1
  loadActiveTab()
}

/**
 * 翻页。
 *
 * @param delta: 页码偏移量
 */
function changePage(delta: number): void {
  const next = page.value + delta
  if (next < 1 || next > totalPages.value) return
  page.value = next
  loadActiveTab()
}

/**
 * 打开食谱详情弹层。
 *
 * @param recipeId: 食谱 ID
 * @throws Error 食谱不存在（40400）时静默忽略
 */
async function openDetail(recipeId: number): Promise<void> {
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getRecipe(recipeId)
  } catch {
    // 忽略详情加载失败
  } finally {
    detailLoading.value = false
  }
}

/**
 * 切换收藏状态并同步列表。
 *
 * @param recipe: 目标食谱
 * @throws Error 接口错误时静默忽略
 */
async function toggleFavorite(recipe: Recipe): Promise<void> {
  try {
    const resp = recipe.is_favorite
      ? await unfavoriteRecipe(recipe.id)
      : await favoriteRecipe(recipe.id)
    recipe.is_favorite = resp.favorited
    if (detail.value && detail.value.id === recipe.id) {
      detail.value.is_favorite = resp.favorited
    }
    // 收藏 Tab 中取消收藏后刷新列表
    if (activeTab.value === 'favorites') {
      favorites.value = await listFavorites()
    }
  } catch {
    // 忽略收藏操作失败
  }
}

/**
 * 在收藏列表中直接取消收藏。
 *
 * @param favorite: 收藏概要
 * @throws Error 接口错误时静默忽略
 */
async function removeFavorite(favorite: RecipeFavorite): Promise<void> {
  try {
    await unfavoriteRecipe(favorite.recipe_id)
    favorites.value = await listFavorites()
  } catch {
    // 忽略取消收藏失败
  }
}

/**
 * 保存一周辅食计划（整体覆盖）。
 *
 * @throws Error 计划项冲突（50000）时展示提示
 */
async function onSavePlan(): Promise<void> {
  const babyId = babyStore.currentBabyId
  if (babyId === null) return
  planSaving.value = true
  planMessage.value = ''
  try {
    const items = Object.entries(planDraft)
      .filter(([, v]) => v.recipeId > 0 || v.note.trim() !== '')
      .map(([key, v]) => {
        const [dayStr, meal] = key.split('-')
        return {
          day_of_week: Number(dayStr),
          meal_type: meal as MealType,
          recipe_id: v.recipeId > 0 ? v.recipeId : null,
          note: v.note.trim() || null
        }
      })
    await saveMealPlans(babyId, weekStart.value, items)
    planMessage.value = '本周辅食计划已保存'
  } catch (err) {
    planMessage.value = err instanceof Error ? err.message : '保存失败，请稍后重试'
  } finally {
    planSaving.value = false
  }
}

/**
 * 食谱适宜月龄文案。
 *
 * @param recipe: 食谱
 * @returns 如 "6-12 月龄"
 */
function ageRangeText(recipe: Recipe): string {
  return `${recipe.suitable_age_min}-${recipe.suitable_age_max} 月龄`
}

// 切换 Tab 或宝宝时重新加载（回到第一页）
watch([activeTab, () => babyStore.currentBabyId], () => {
  page.value = 1
  loadActiveTab()
})

// 切换周时重新加载计划
watch(weekStart, () => {
  if (activeTab.value === 'plan') loadActiveTab()
})

// 组件挂载：加载宝宝列表与默认 Tab 数据（列表经 store 缓存去重）
onMounted(async () => {
  await babyStore.ensureLoaded().catch(() => undefined)
  await loadActiveTab()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">食谱推荐</h1>

    <ErrorState v-if="error && !loading" :message="error" @retry="loadActiveTab" />

    <!-- Tab 切换 -->
    <div class="tabs">
      <button
        v-for="tab in [
          { key: 'all', label: '全部食谱' },
          { key: 'favorites', label: '我的收藏' },
          { key: 'recommend', label: '智能推荐' },
          { key: 'plan', label: '一周计划' }
        ]"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="activeTab = tab.key as typeof activeTab"
      >
        {{ tab.label }}
      </button>
    </div>

    <LoadingState v-if="loading" text="正在加载…" />

    <template v-else>
      <!-- 全部食谱：筛选区 -->
      <section v-if="activeTab === 'all'" class="card filter-card">
        <div class="filter-grid">
          <div class="field">
            <label class="label" for="f-keyword">名称搜索</label>
            <input id="f-keyword" v-model="filters.keyword" class="input" type="text" placeholder="如：南瓜" @keyup.enter="applyFilters" />
          </div>
          <div class="field">
            <label class="label" for="f-age">适宜月龄</label>
            <input id="f-age" v-model="filters.age_months" class="input" type="number" min="0" max="36" placeholder="如 8" />
          </div>
          <div class="field">
            <label class="label" for="f-ingredient">食材</label>
            <input id="f-ingredient" v-model="filters.ingredient" class="input" type="text" placeholder="如：牛肉" @keyup.enter="applyFilters" />
          </div>
          <div class="field">
            <label class="label" for="f-nutrition">营养标签</label>
            <input id="f-nutrition" v-model="filters.nutrition" class="input" type="text" placeholder="如：补铁" @keyup.enter="applyFilters" />
          </div>
        </div>
        <button class="btn btn-primary apply-btn" type="button" @click="applyFilters">筛选</button>
      </section>

      <!-- 智能推荐提示 -->
      <p v-if="activeTab === 'recommend'" class="recommend-tip">
        基于宝宝月龄与过敏史推荐
        {{ babyStore.currentBaby ? `（${babyStore.currentBaby.name}）` : '' }}，
        已自动规避过敏食材
      </p>

      <!-- 食谱网格（全部 / 推荐） -->
      <template v-if="activeTab === 'all' || activeTab === 'recommend'">
        <EmptyState
          v-if="activeTab === 'recommend' && babyStore.babies.length === 0"
          text="请先在「宝宝概览」创建宝宝档案后再使用智能推荐"
        />
        <EmptyState v-else-if="recipes.length === 0" text="没有符合条件的食谱" />
        <div v-else class="recipe-grid">
          <article v-for="r in recipes" :key="r.id" class="card recipe-card">
            <button class="recipe-main" type="button" @click="openDetail(r.id)">
              <h3 class="recipe-title">{{ r.title }}</h3>
              <p class="recipe-age">{{ ageRangeText(r) }}</p>
              <div class="recipe-tags">
                <span v-for="t in r.nutrition_tags.slice(0, 3)" :key="t" class="tag tag-green">{{ t }}</span>
              </div>
            </button>
            <button class="fav-btn" type="button" :title="r.is_favorite ? '取消收藏' : '收藏'" @click="toggleFavorite(r)">
              {{ r.is_favorite ? '★' : '☆' }}
            </button>
          </article>
        </div>
        <div v-if="total > pageSize" class="pager">
          <button class="btn btn-ghost btn-sm" type="button" :disabled="page <= 1" @click="changePage(-1)">上一页</button>
          <span class="tabular">第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
          <button class="btn btn-ghost btn-sm" type="button" :disabled="page >= totalPages" @click="changePage(1)">下一页</button>
        </div>
      </template>

      <!-- 我的收藏 -->
      <template v-else-if="activeTab === 'favorites'">
        <EmptyState v-if="favorites.length === 0" text="还没有收藏食谱，去全部食谱里逛逛吧" />
        <ul v-else class="fav-list">
          <li v-for="f in favorites" :key="f.id" class="card fav-item">
            <button class="fav-main" type="button" @click="openDetail(f.recipe_id)">
              <span class="fav-title">{{ f.recipe_title }}</span>
              <span class="fav-date tabular">收藏于 {{ f.created_at.slice(0, 10) }}</span>
            </button>
            <button class="link-danger" type="button" @click="removeFavorite(f)">取消收藏</button>
          </li>
        </ul>
      </template>

      <!-- 一周计划 -->
      <template v-else-if="activeTab === 'plan'">
        <EmptyState
          v-if="babyStore.babies.length === 0"
          text="请先在「宝宝概览」创建宝宝档案后再安排辅食计划"
        />
        <template v-else>
          <div class="row plan-toolbar">
            <div class="field">
              <label class="label" for="week-start">周起始（周一）</label>
              <input id="week-start" v-model="weekStart" class="input" type="date" />
            </div>
            <button class="btn btn-primary" type="button" :disabled="planSaving" @click="onSavePlan">
              {{ planSaving ? '保存中…' : '保存本周计划' }}
            </button>
          </div>
          <p v-if="planMessage" class="plan-message" role="status">{{ planMessage }}</p>

          <div class="plan-board">
            <div v-for="d in 7" :key="d" class="card plan-day">
              <h3 class="plan-day-title">
                {{ dayLabels[d - 1] }}
                <span class="plan-date tabular">{{ dateOfDay(d - 1).slice(5) }}</span>
              </h3>
              <div v-for="meal in mealTypes" :key="meal.value" class="plan-meal">
                <span class="meal-label">{{ meal.label }}</span>
                <select
                  class="select plan-select"
                  :value="planDraft[planKey(d - 1, meal.value)]?.recipeId ?? 0"
                  :aria-label="`${dayLabels[d - 1]}${meal.label}`"
                  @change="
                    planDraft[planKey(d - 1, meal.value)] &&
                      (planDraft[planKey(d - 1, meal.value)]!.recipeId = Number(
                        ($event.target as HTMLSelectElement).value
                      ))
                  "
                >
                  <option :value="0">待定</option>
                  <option v-for="r in recipes" :key="r.id" :value="r.id">{{ r.title }}</option>
                </select>
                <input
                  class="input plan-note"
                  type="text"
                  maxlength="200"
                  placeholder="备注"
                  :value="planDraft[planKey(d - 1, meal.value)]?.note ?? ''"
                  @input="
                    planDraft[planKey(d - 1, meal.value)] &&
                      (planDraft[planKey(d - 1, meal.value)]!.note = ($event.target as HTMLInputElement).value)
                  "
                />
              </div>
            </div>
          </div>
        </template>
      </template>
    </template>

    <!-- 食谱详情弹层 -->
    <AppModal v-if="detail" :title="detail.title" @close="detail = null">
      <div class="detail-body">
        <div class="row detail-meta">
          <span class="tag">{{ ageRangeText(detail) }}</span>
          <span v-for="t in detail.nutrition_tags" :key="t" class="tag tag-green">{{ t }}</span>
        </div>
        <h3 class="detail-sub">食材</h3>
        <ul class="detail-list">
          <li v-for="(item, i) in ingredientTexts" :key="i">{{ item }}</li>
        </ul>
        <h3 class="detail-sub">步骤</h3>
        <ol class="detail-list steps">
          <li v-for="(s, i) in detail.steps" :key="i">{{ s }}</li>
        </ol>
        <template v-if="detail.tips">
          <h3 class="detail-sub">小贴士</h3>
          <p class="detail-tips">{{ detail.tips }}</p>
        </template>
        <button class="btn detail-fav-btn" :class="detail.is_favorite ? 'btn-ghost' : 'btn-primary'" type="button" @click="toggleFavorite(detail)">
          {{ detail.is_favorite ? '★ 已收藏 · 点击取消' : '☆ 收藏该食谱' }}
        </button>
      </div>
    </AppModal>

    <!-- 详情加载态 -->
    <AppModal v-else-if="detailLoading" title="加载中…" @close="detailLoading = false">
      <LoadingState text="正在加载食谱详情…" />
    </AppModal>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
  overflow-x: auto;
}

.tab-btn {
  border: 1.5px solid var(--color-border-strong);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  padding: 8px 18px;
  border-radius: var(--radius-full);
  cursor: pointer;
  white-space: nowrap;
}

.tab-btn.active {
  background: var(--color-primary-strong);
  border-color: var(--color-primary-strong);
  color: var(--color-on-primary);
  font-weight: 600;
}

.filter-card {
  margin-bottom: var(--space-lg);
}

.filter-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.field {
  display: flex;
  flex-direction: column;
}

.recommend-tip {
  margin: 0 0 var(--space-lg);
  color: var(--color-text-secondary);
  font-size: 13px;
}

.recipe-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
}

.recipe-card {
  position: relative;
  padding: 0;
  overflow: hidden;
}

.recipe-main {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  border: none;
  color: inherit;
  font-family: inherit;
  padding: var(--space-lg);
  cursor: pointer;
}

.recipe-title {
  font-size: 16px;
  padding-right: 32px;
}

.recipe-age {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.recipe-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

.fav-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  background: transparent;
  border: none;
  color: var(--color-tertiary);
  font-size: 20px;
  cursor: pointer;
  padding: 4px;
}

.fav-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.fav-item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
}

.fav-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  background: transparent;
  border: none;
  color: inherit;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
}

.fav-title {
  font-size: 15px;
  font-weight: 600;
}

.fav-date {
  font-size: 12px;
  color: var(--color-text-muted);
}

.link-danger {
  background: transparent;
  border: none;
  color: var(--color-danger);
  font-size: 13px;
  cursor: pointer;
  padding: 0;
}

.link-danger:hover {
  text-decoration: underline;
}

.plan-toolbar {
  align-items: flex-end;
  margin-bottom: var(--space-md);
}

.plan-message {
  margin: 0 0 var(--space-md);
  color: var(--color-secondary);
  font-size: 13px;
}

.plan-board {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
}

.plan-day-title {
  font-size: 15px;
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.plan-date {
  font-size: 12px;
  color: var(--color-text-muted);
}

.plan-meal {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.meal-label {
  width: 36px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.plan-select {
  flex: 1;
  min-width: 0;
}

.plan-note {
  max-width: 120px;
}

/* 详情弹层 */
.detail-body {
  display: flex;
  flex-direction: column;
}

.detail-meta {
  flex-wrap: wrap;
  margin-bottom: var(--space-md);
}

.detail-sub {
  font-size: 15px;
  margin: var(--space-md) 0 var(--space-sm);
  color: var(--color-primary);
}

.detail-list {
  margin: 0;
  padding-left: 20px;
  font-size: 14px;
  line-height: 22px;
}

.detail-list.steps li {
  margin-bottom: var(--space-xs);
}

.detail-tips {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  background: rgba(231, 195, 98, 0.1);
  border-radius: var(--radius-sm);
  padding: var(--space-md);
}

.detail-fav-btn {
  margin-top: var(--space-lg);
}

@media (min-width: 768px) {
  .filter-grid {
    grid-template-columns: repeat(4, 1fr);
  }

  .recipe-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .plan-board {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
