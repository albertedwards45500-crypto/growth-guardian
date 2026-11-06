<script setup lang="ts">
/**
 * @file: src/views/DietRecords.vue
 * @description: 饮食记录页：日期筛选分页列表、三类记录新增（母乳/配方奶/辅食）、营养分析与过敏食材管理。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useBabyStore } from '@/stores/baby'
import {
  createAllergy,
  createDietRecord,
  deleteAllergy,
  deleteDietRecord,
  getDietAnalysis,
  listAllergies,
  listDietRecords
} from '@/api/diet'
import type { Allergy, AllergySeverity, DietRecord, DietType, NutritionSummary } from '@/types/api'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import AppModal from '@/components/AppModal.vue'

// 宝宝 store
const babyStore = useBabyStore()

// 页面状态
const loading = ref(false)
const error = ref('')

// 记录列表与分页
const records = ref<DietRecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
// 筛选日期（空字符串表示全部）
const filterDate = ref('')

// 营养分析
const analysis = ref<NutritionSummary | null>(null)

// 过敏食材
const allergies = ref<Allergy[]>([])

// 新增记录弹层状态
const showForm = ref(false)
const saving = ref(false)
const formError = ref('')
// 记录表单
const form = reactive<{
  record_date: string
  record_type: DietType
  left_minutes: string
  right_minutes: string
  amount_ml: string
  food_items: string
  note: string
}>({
  record_date: new Date().toISOString().slice(0, 10),
  record_type: 'breast_milk',
  left_minutes: '',
  right_minutes: '',
  amount_ml: '',
  food_items: '',
  note: ''
})

// 过敏食材表单状态
const allergyIngredient = ref('')
const allergySeverity = ref<AllergySeverity | ''>('')
const allergyError = ref('')

// 今天日期字符串（日期上限）
const todayStr = new Date().toISOString().slice(0, 10)

// 记录类型元信息
const typeMeta: Record<DietType, { label: string; tag: string }> = {
  breast_milk: { label: '母乳', tag: 'tag tag-yellow' },
  formula: { label: '配方奶', tag: 'tag tag-blue' },
  solid_food: { label: '辅食', tag: 'tag tag-green' }
}

/** 总页数（至少 1 页） */
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

/**
 * 解析饮食记录明细为可读文案。
 *
 * @param record: 饮食记录
 * @returns 明细摘要文案
 */
function detailText(record: DietRecord): string {
  const d = record.details ?? {}
  if (record.record_type === 'breast_milk') {
    const parts: string[] = []
    const left = Number(d['left_minutes'] ?? 0)
    const right = Number(d['right_minutes'] ?? 0)
    if (left) parts.push(`左侧 ${left} 分钟`)
    if (right) parts.push(`右侧 ${right} 分钟`)
    return parts.join(' + ') || '已记录'
  }
  if (record.record_type === 'formula') {
    return `${Number(d['amount_ml'] ?? 0)} ml`
  }
  const foods = Array.isArray(d['food_items']) ? (d['food_items'] as unknown[]) : []
  return foods.map((f) => String(f)).join('、') || '已记录'
}

/**
 * 加载记录列表、营养分析与过敏食材。
 *
 * @throws Error 网络错误时展示错误态
 */
async function loadAll(): Promise<void> {
  const babyId = babyStore.currentBabyId
  if (babyId === null) {
    records.value = []
    allergies.value = []
    analysis.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const today = new Date().toISOString().slice(0, 10)
    const params: { record_date?: string; page: number; page_size: number } = {
      page: page.value,
      page_size: pageSize
    }
    if (filterDate.value) params.record_date = filterDate.value
    const [listResp, allergyList, analysisResp] = await Promise.all([
      listDietRecords(babyId, params),
      listAllergies(babyId),
      getDietAnalysis(babyId, filterDate.value || today)
    ])
    records.value = listResp.items
    total.value = listResp.total
    allergies.value = allergyList
    analysis.value = analysisResp
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

/**
 * 翻页并重新加载。
 *
 * @param delta: 页码偏移量
 */
function changePage(delta: number): void {
  const next = page.value + delta
  if (next < 1 || next > totalPages.value) return
  page.value = next
  loadAll()
}

/**
 * 打开新增记录弹层。
 */
function openForm(): void {
  form.record_date = filterDate.value || new Date().toISOString().slice(0, 10)
  form.record_type = 'breast_milk'
  form.left_minutes = ''
  form.right_minutes = ''
  form.amount_ml = ''
  form.food_items = ''
  form.note = ''
  formError.value = ''
  showForm.value = true
}

/**
 * 校验并组装当前类型的明细字段。
 *
 * @returns 校验通过返回明细对象，否则返回 null
 */
function buildDetails(): Record<string, unknown> | null {
  if (form.record_type === 'breast_milk') {
    const left = Number(form.left_minutes) || 0
    const right = Number(form.right_minutes) || 0
    if (!left && !right) {
      formError.value = '母乳记录需填写喂养时长'
      return null
    }
    return { left_minutes: left, right_minutes: right }
  }
  if (form.record_type === 'formula') {
    const amount = Number(form.amount_ml)
    if (!amount) {
      formError.value = '配方奶记录需填写奶量(ml)'
      return null
    }
    return { amount_ml: amount }
  }
  const items = form.food_items
    .split(/[、,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (items.length === 0) {
    formError.value = '辅食记录需填写食材清单'
    return null
  }
  return { food_items: items }
}

/**
 * 保存饮食记录。
 *
 * @throws Error 明细不匹配（40002）或接口校验失败时展示错误
 */
async function onSave(): Promise<void> {
  if (saving.value) return
  const babyId = babyStore.currentBabyId
  if (babyId === null) return
  formError.value = ''
  const details = buildDetails()
  if (details === null) return
  saving.value = true
  try {
    await createDietRecord(babyId, {
      record_date: form.record_date,
      record_type: form.record_type,
      details,
      note: form.note.trim() || null
    })
    showForm.value = false
    page.value = 1
    await loadAll()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

/**
 * 删除饮食记录。
 *
 * @param record: 目标记录
 * @throws Error 接口错误时静默忽略
 */
async function onDelete(record: DietRecord): Promise<void> {
  if (!window.confirm('确定删除这条饮食记录吗？')) return
  try {
    await deleteDietRecord(record.id)
    await loadAll()
  } catch {
    // 忽略删除失败
  }
}

/**
 * 新增过敏食材。
 *
 * @throws Error 食材重复（40900）时展示错误
 */
async function onAddAllergy(): Promise<void> {
  const babyId = babyStore.currentBabyId
  if (babyId === null) return
  const ingredient = allergyIngredient.value.trim()
  if (!ingredient) {
    allergyError.value = '请输入食材名称'
    return
  }
  allergyError.value = ''
  try {
    await createAllergy(babyId, {
      ingredient,
      severity: allergySeverity.value === '' ? null : allergySeverity.value
    })
    allergyIngredient.value = ''
    allergySeverity.value = ''
    allergies.value = await listAllergies(babyId)
  } catch (err) {
    allergyError.value = err instanceof Error ? err.message : '添加失败，请稍后重试'
  }
}

/**
 * 删除过敏食材。
 *
 * @param allergy: 目标记录
 * @throws Error 接口错误时静默忽略
 */
async function onDeleteAllergy(allergy: Allergy): Promise<void> {
  if (!window.confirm(`确定移除过敏食材「${allergy.ingredient}」吗？`)) return
  const babyId = babyStore.currentBabyId
  if (babyId === null) return
  try {
    await deleteAllergy(allergy.id)
    allergies.value = await listAllergies(babyId)
  } catch {
    // 忽略删除失败
  }
}

/**
 * 过敏严重程度转中文文案。
 *
 * @param severity: 严重程度编码
 * @returns 中文文案
 */
function severityText(severity: AllergySeverity | null): string {
  const map: Record<string, string> = { mild: '轻度', moderate: '中度', severe: '重度' }
  return severity ? (map[severity] ?? severity) : '未标注'
}

// 筛选日期或当前宝宝变化时回到第一页并重新加载
watch([filterDate, () => babyStore.currentBabyId], () => {
  page.value = 1
  loadAll()
})

// 组件挂载：加载数据（列表经 store 缓存去重）
onMounted(async () => {
  await babyStore.ensureLoaded().catch(() => undefined)
  await loadAll()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">饮食记录</h1>

    <EmptyState
      v-if="!loading && !error && babyStore.babies.length === 0"
      text="请先在「宝宝概览」创建宝宝档案"
    />

    <template v-else>
      <ErrorState v-if="error && !loading" :message="error" @retry="loadAll" />
      <LoadingState v-else-if="loading" text="正在加载饮食数据…" />

      <template v-else>
        <!-- 工具行：日期筛选 + 新增 -->
        <div class="row toolbar">
          <div class="grow">
            <label class="label" for="diet-date">按日期筛选</label>
            <input id="diet-date" v-model="filterDate" class="input" type="date" />
          </div>
          <button class="btn btn-primary" type="button" @click="openForm">+ 新增记录</button>
        </div>

        <!-- 营养分析卡片 -->
        <section v-if="analysis" class="card analysis-card">
          <div class="row section-head">
            <h2 class="section-title">{{ analysis.date }} 营养分析</h2>
          </div>
          <div class="analysis-grid">
            <div class="analysis-item">
              <span class="num tabular">{{ analysis.feed_count }}</span>
              <span class="label-text">喂养次数</span>
            </div>
            <div class="analysis-item">
              <span class="num tabular">{{ analysis.breast_milk_minutes }}</span>
              <span class="label-text">母乳时长 (分钟)</span>
            </div>
            <div class="analysis-item">
              <span class="num tabular">{{ analysis.formula_amount_ml }}</span>
              <span class="label-text">配方奶 (ml)</span>
            </div>
            <div class="analysis-item">
              <span class="num tabular">{{ analysis.solid_food_count }}</span>
              <span class="label-text">辅食次数</span>
            </div>
          </div>
          <p v-if="analysis.food_names.length" class="food-names">
            今日食材：<span v-for="f in analysis.food_names" :key="f" class="tag tag-green">{{ f }}</span>
          </p>
        </section>

        <!-- 记录列表 -->
        <section class="section">
          <h2 class="section-title">记录列表</h2>
          <EmptyState v-if="records.length === 0" text="这一天还没有饮食记录" />
          <ul v-else class="record-list">
            <li v-for="r in records" :key="r.id" class="card record-item">
              <div class="row record-top">
                <span :class="typeMeta[r.record_type]?.tag ?? 'tag'">
                  {{ typeMeta[r.record_type]?.label ?? r.record_type }}
                </span>
                <span class="date tabular">{{ r.record_date }}</span>
                <button class="link-danger" type="button" @click="onDelete(r)">删除</button>
              </div>
              <p class="detail">{{ detailText(r) }}</p>
              <p v-if="r.note" class="note">{{ r.note }}</p>
            </li>
          </ul>
          <div v-if="total > pageSize" class="pager">
            <button class="btn btn-ghost btn-sm" type="button" :disabled="page <= 1" @click="changePage(-1)">
              上一页
            </button>
            <span class="tabular">第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
            <button
              class="btn btn-ghost btn-sm"
              type="button"
              :disabled="page >= totalPages"
              @click="changePage(1)"
            >
              下一页
            </button>
          </div>
        </section>

        <!-- 过敏食材管理 -->
        <section class="section">
          <h2 class="section-title">过敏食材</h2>
          <div class="card allergy-card">
            <form class="row allergy-form" novalidate @submit.prevent="onAddAllergy">
              <input
                v-model="allergyIngredient"
                class="input grow"
                type="text"
                maxlength="50"
                placeholder="食材名称，如：鸡蛋"
              />
              <select v-model="allergySeverity" class="select severity-select" aria-label="严重程度">
                <option value="">未标注</option>
                <option value="mild">轻度</option>
                <option value="moderate">中度</option>
                <option value="severe">重度</option>
              </select>
              <button class="btn btn-primary" type="submit">添加</button>
            </form>
            <p v-if="allergyError" class="form-error" role="alert">{{ allergyError }}</p>
            <EmptyState v-if="allergies.length === 0" text="暂无过敏食材记录" />
            <ul v-else class="allergy-list">
              <li v-for="a in allergies" :key="a.id" class="allergy-item">
                <span class="ingredient">{{ a.ingredient }}</span>
                <span class="tag" :class="a.severity === 'severe' ? 'tag-red' : 'tag-yellow'">
                  {{ severityText(a.severity) }}
                </span>
                <button class="link-danger" type="button" @click="onDeleteAllergy(a)">移除</button>
              </li>
            </ul>
          </div>
        </section>
      </template>
    </template>

    <!-- 新增记录弹层 -->
    <AppModal v-if="showForm" title="新增饮食记录" @close="showForm = false">
      <form class="form" novalidate @submit.prevent="onSave">
        <div class="field">
          <label class="label" for="d-date">记录日期</label>
          <input id="d-date" v-model="form.record_date" class="input" type="date" :max="todayStr" />
        </div>
        <div class="field">
          <span class="label">记录类型</span>
          <div class="type-tabs">
            <button
              v-for="(meta, type) in typeMeta"
              :key="type"
              class="type-tab"
              :class="{ active: form.record_type === type }"
              type="button"
              @click="form.record_type = type as DietType"
            >
              {{ meta.label }}
            </button>
          </div>
        </div>

        <!-- 母乳明细 -->
        <div v-if="form.record_type === 'breast_milk'" class="field-grid">
          <div class="field">
            <label class="label" for="d-left">左侧 (分钟)</label>
            <input id="d-left" v-model="form.left_minutes" class="input" type="number" min="0" max="120" placeholder="0" />
          </div>
          <div class="field">
            <label class="label" for="d-right">右侧 (分钟)</label>
            <input id="d-right" v-model="form.right_minutes" class="input" type="number" min="0" max="120" placeholder="0" />
          </div>
        </div>
        <!-- 配方奶明细 -->
        <div v-else-if="form.record_type === 'formula'" class="field">
          <label class="label" for="d-amount">奶量 (ml)</label>
          <input id="d-amount" v-model="form.amount_ml" class="input" type="number" min="0" max="2000" placeholder="如 150" />
        </div>
        <!-- 辅食明细 -->
        <div v-else class="field">
          <label class="label" for="d-foods">食材清单</label>
          <textarea
            id="d-foods"
            v-model="form.food_items"
            class="textarea"
            rows="2"
            placeholder="多种食材用顿号或逗号分隔，如：米粉、南瓜泥"
          />
        </div>

        <div class="field">
          <label class="label" for="d-note">备注（选填）</label>
          <textarea id="d-note" v-model="form.note" class="textarea" rows="2" maxlength="500" />
        </div>

        <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
        <div class="row form-actions">
          <button class="btn btn-ghost grow" type="button" @click="showForm = false">取消</button>
          <button class="btn btn-primary grow" type="submit" :disabled="saving">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </form>
    </AppModal>
  </div>
</template>

<style scoped>
.toolbar {
  align-items: flex-end;
  margin-bottom: var(--space-lg);
}

.section {
  margin-bottom: var(--space-xl);
}

.section-title {
  font-size: 17px;
  font-weight: 600;
  margin-bottom: var(--space-md);
}

.analysis-card {
  margin-bottom: var(--space-xl);
}

.section-head {
  justify-content: space-between;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-md);
}

.analysis-item {
  background: rgba(23, 19, 15, 0.5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.num {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 700;
  color: var(--color-primary);
}

.label-text {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.food-names {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
  margin: var(--space-md) 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.record-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.record-item {
  padding: var(--space-md) var(--space-lg);
}

.record-top {
  gap: var(--space-sm);
}

.date {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-secondary);
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

.detail {
  margin: var(--space-xs) 0 0;
  font-size: 15px;
}

.note {
  margin: var(--space-xs) 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.allergy-card {
  padding: var(--space-lg);
}

.allergy-form {
  flex-wrap: wrap;
}

.severity-select {
  max-width: 110px;
}

.allergy-list {
  list-style: none;
  margin: var(--space-md) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.allergy-item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--color-border);
}

.allergy-item:last-child {
  border-bottom: none;
}

.ingredient {
  flex: 1;
  font-size: 14px;
}

.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.field {
  display: flex;
  flex-direction: column;
}

.type-tabs {
  display: flex;
  gap: 4px;
  background: var(--color-surface-high);
  border-radius: var(--radius-sm);
  padding: 3px;
}

.type-tab {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 6px 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.type-tab.active {
  background: var(--color-primary-strong);
  color: var(--color-on-primary);
  font-weight: 600;
}

.field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.form-error {
  margin: 0;
  color: var(--color-danger);
  font-size: 13px;
}

.form-actions {
  margin-top: var(--space-sm);
}

@media (min-width: 768px) {
  .analysis-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
</style>
