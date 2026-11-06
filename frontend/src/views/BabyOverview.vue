<script setup lang="ts">
/**
 * @file: src/views/BabyOverview.vue
 * @description: 宝宝概览页：宝宝档案列表（创建/编辑/设为默认）与成长印记 summary 卡片。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useBabyStore } from '@/stores/baby'
import { createBaby, deleteBaby, updateBaby } from '@/api/babies'
import { getBabySummary } from '@/api/babies'
import type { Baby, Gender, GrowthSummary } from '@/types/api'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import AppModal from '@/components/AppModal.vue'

// 宝宝 store
const babyStore = useBabyStore()

// 页面加载状态：loading 加载中 / error 错误信息
const loading = ref(false)
const error = ref('')

// 成长印记数据
const summary = ref<GrowthSummary | null>(null)
const summaryLoading = ref(false)

// 弹层可见性
const showModal = ref(false)
// 编辑目标（null 表示新建）
const editing = ref<Baby | null>(null)
// 提交中标记
const saving = ref(false)
// 表单错误
const formError = ref('')

// 表单数据
const form = reactive<{ name: string; gender: Gender | ''; birth_date: string }>({
  name: '',
  gender: '',
  birth_date: ''
})

// 今天日期字符串（出生日期上限）
const todayStr = new Date().toISOString().slice(0, 10)

/** 当前宝宝的成长印记副标题 */
const summarySubtitle = computed(() =>
  summary.value ? `${summary.value.stage_name} · 满 ${summary.value.age_months} 月龄` : ''
)

/**
 * 里程碑类型编码 → 中文名映射（与后端 MILESTONE_TYPES 保持一致）。
 */
const MILESTONE_LABELS: Record<string, string> = {
  roll_over: '翻身',
  sit: '独坐',
  crawl: '爬行',
  stand: '扶站',
  walk: '行走',
  run: '跑跳',
  talk: '说话'
}

/**
 * 将成长印记的 milestone_progress 解析为可直接渲染的标签列表。
 *
 * 后端键格式为 `{milestone_type}_{中文名}`（如 roll_over_翻身），
 * 这里按固定顺序输出中文标签与达成状态，避免原始键泄漏到界面。
 *
 * @returns 标签列表：{ type 类型编码, name 中文名, done 是否达成 }
 */
const milestoneTags = computed<{ type: string; name: string; done: boolean }[]>(() => {
  const progress = summary.value?.milestone_progress ?? {}
  const tags: { type: string; name: string; done: boolean }[] = []
  for (const [key, count] of Object.entries(progress)) {
    const sep = key.lastIndexOf('_')
    const mtype = sep > 0 ? key.slice(0, sep) : key
    // 优先取映射表中文名；未知类型回退取键中 `_` 之后的中文段
    const name = MILESTONE_LABELS[mtype] ?? (sep > 0 ? key.slice(sep + 1) : key)
    tags.push({ type: mtype, name, done: count > 0 })
  }
  const order = Object.keys(MILESTONE_LABELS)
  return tags.sort((a, b) => order.indexOf(a.type) - order.indexOf(b.type))
})

/** 性别展示文案 */
function genderText(gender: Gender | null): string {
  return gender === 'male' ? '男宝' : gender === 'female' ? '女宝' : '未设置'
}

/**
 * 拉取宝宝列表与成长印记。
 *
 * 列表经由 store 的 ensureLoaded 复用缓存，避免与布局层重复请求。
 *
 * @throws Error 网络错误时展示错误态
 */
async function loadAll(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    await babyStore.ensureLoaded()
    await loadSummary()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

/**
 * 拉取当前宝宝的成长印记数据。
 *
 * @throws Error 接口错误时静默置空
 */
async function loadSummary(): Promise<void> {
  const babyId = babyStore.currentBabyId
  if (babyId === null) {
    summary.value = null
    return
  }
  summaryLoading.value = true
  try {
    summary.value = await getBabySummary(babyId)
  } catch {
    summary.value = null
  } finally {
    summaryLoading.value = false
  }
}

/**
 * 打开新建宝宝弹层。
 */
function openCreate(): void {
  editing.value = null
  form.name = ''
  form.gender = ''
  form.birth_date = ''
  formError.value = ''
  showModal.value = true
}

/**
 * 打开编辑宝宝弹层（预填当前档案）。
 *
 * @param baby: 待编辑的宝宝
 */
function openEdit(baby: Baby): void {
  editing.value = baby
  form.name = baby.name
  form.gender = baby.gender ?? ''
  form.birth_date = baby.birth_date
  formError.value = ''
  showModal.value = true
}

/**
 * 校验宝宝表单。
 *
 * @returns 校验通过返回 true
 */
function validate(): boolean {
  if (!form.name.trim()) {
    formError.value = '请填写宝宝昵称'
    return false
  }
  if (!form.birth_date) {
    formError.value = '请选择出生日期'
    return false
  }
  const today = new Date().toISOString().slice(0, 10)
  if (form.birth_date > today) {
    formError.value = '出生日期不能晚于今天'
    return false
  }
  formError.value = ''
  return true
}

/**
 * 保存宝宝档案（新建或更新）。
 *
 * @throws Error 接口校验失败（42200）时展示错误
 */
async function onSave(): Promise<void> {
  if (!validate() || saving.value) return
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      gender: form.gender === '' ? null : (form.gender as Gender),
      birth_date: form.birth_date
    }
    if (editing.value) {
      await updateBaby(editing.value.id, payload)
    } else {
      await createBaby(payload)
    }
    showModal.value = false
    await babyStore.fetchBabies()
    await loadSummary()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

/**
 * 将指定宝宝设为默认档案。
 *
 * @param baby: 目标宝宝
 * @throws Error 接口错误时静默忽略
 */
async function setDefault(baby: Baby): Promise<void> {
  try {
    await updateBaby(baby.id, { is_default: true })
    await babyStore.fetchBabies()
  } catch {
    // 忽略设默认失败
  }
}

/**
 * 删除宝宝档案（需二次确认）。
 *
 * @param baby: 目标宝宝
 * @throws Error 接口错误时静默忽略
 */
async function onDelete(baby: Baby): Promise<void> {
  if (!window.confirm(`确定删除「${baby.name}」的档案吗？其记录将一并删除。`)) return
  try {
    await deleteBaby(baby.id)
    await babyStore.fetchBabies()
    await loadSummary()
  } catch {
    // 忽略删除失败
  }
}

// 组件挂载：加载列表与成长印记
onMounted(loadAll)
</script>

<template>
  <div class="page">
    <h1 class="page-title">宝宝概览</h1>

    <!-- 错误态 -->
    <ErrorState v-if="error && !loading" :message="error" @retry="loadAll" />
    <!-- 加载态 -->
    <LoadingState v-else-if="loading" text="正在加载宝宝档案…" />

    <template v-else>
      <!-- 成长印记卡片 -->
      <section v-if="summary" class="card imprint-card">
        <h2 class="imprint-title">成长印记</h2>
        <div class="imprint-head">
          <div class="avatar-lg" aria-hidden="true">{{ summary.baby_name.slice(0, 1) }}</div>
          <div>
            <h3 class="imprint-name">{{ summary.baby_name }}</h3>
            <p class="imprint-sub">{{ summarySubtitle }}</p>
          </div>
        </div>
        <div class="imprint-grid">
          <div class="imprint-item">
            <span class="imprint-num tabular">{{ summary.latest_weight_kg ?? '--' }}</span>
            <span class="imprint-label">体重 (kg)</span>
          </div>
          <div class="imprint-item">
            <span class="imprint-num tabular">{{ summary.latest_height_cm ?? '--' }}</span>
            <span class="imprint-label">身长 (cm)</span>
          </div>
          <div class="imprint-item">
            <span class="imprint-num tabular">
              {{ summary.latest_head_circumference_cm ?? '--' }}
            </span>
            <span class="imprint-label">头围 (cm)</span>
          </div>
          <div class="imprint-item">
            <span class="imprint-num tabular">{{ summary.age_days }}</span>
            <span class="imprint-label">成长天数</span>
          </div>
        </div>
        <p class="imprint-date" v-if="summary.latest_measure_date">
          最近测量：{{ summary.latest_measure_date }}
        </p>
        <div class="milestone-progress" v-if="milestoneTags.length">
          <span
            v-for="tag in milestoneTags"
            :key="tag.type"
            class="tag"
            :class="tag.done ? 'tag-green' : 'tag-yellow'"
          >
            {{ tag.name }} {{ tag.done ? '✓' : '✗' }}
          </span>
        </div>
        <RouterLink class="btn btn-ghost btn-sm advisor-entry" :to="{ name: 'advisor' }">让成长顾问整理记录 →</RouterLink>
      </section>

      <!-- 宝宝档案列表 -->
      <section class="section">
        <div class="row section-head">
          <h2 class="section-title">宝宝档案</h2>
          <button class="btn btn-primary btn-sm" type="button" @click="openCreate">+ 添加宝宝</button>
        </div>

        <EmptyState v-if="babyStore.babies.length === 0" text="还没有宝宝档案，先创建一个吧">
          <button class="btn btn-primary" type="button" @click="openCreate">创建宝宝档案</button>
        </EmptyState>

        <div v-else class="baby-grid">
          <article
            v-for="baby in babyStore.babies"
            :key="baby.id"
            class="card baby-card"
            :class="{ active: baby.id === babyStore.currentBabyId }"
          >
            <div class="row">
              <div class="avatar-md" aria-hidden="true">{{ baby.name.slice(0, 1) }}</div>
              <div class="grow">
                <h3 class="baby-name">
                  {{ baby.name }}
                  <span v-if="baby.is_default" class="tag tag-yellow">默认</span>
                </h3>
                <p class="baby-meta">{{ genderText(baby.gender) }} · {{ baby.birth_date }}</p>
              </div>
            </div>
            <div class="baby-actions">
              <button
                v-if="baby.id !== babyStore.currentBabyId"
                class="btn btn-ghost btn-sm"
                type="button"
                @click="babyStore.setCurrentBaby(baby.id)"
              >
                查看档案
              </button>
              <button
                v-if="!baby.is_default"
                class="btn btn-ghost btn-sm"
                type="button"
                @click="setDefault(baby)"
              >
                设为默认
              </button>
              <button class="btn btn-ghost btn-sm" type="button" @click="openEdit(baby)">编辑</button>
              <button class="btn btn-danger-ghost btn-sm" type="button" @click="onDelete(baby)">
                删除
              </button>
            </div>
          </article>
        </div>
      </section>
    </template>

    <!-- 新建/编辑弹层 -->
    <AppModal v-if="showModal" :title="editing ? `编辑「${editing.name}」` : '创建宝宝档案'" @close="showModal = false">
      <form class="form" novalidate @submit.prevent="onSave">
        <div class="field">
          <label class="label" for="baby-name">宝宝昵称</label>
          <input id="baby-name" v-model="form.name" class="input" type="text" maxlength="50" placeholder="如：豆豆" />
        </div>
        <div class="field">
          <label class="label" for="baby-gender">性别</label>
          <select id="baby-gender" v-model="form.gender" class="select">
            <option value="">未设置</option>
            <option value="male">男宝</option>
            <option value="female">女宝</option>
          </select>
        </div>
        <div class="field">
          <label class="label" for="baby-birth">出生日期</label>
          <input id="baby-birth" v-model="form.birth_date" class="input" type="date" :max="todayStr" />
        </div>
        <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
        <div class="row form-actions">
          <button class="btn btn-ghost grow" type="button" @click="showModal = false">取消</button>
          <button class="btn btn-primary grow" type="submit" :disabled="saving">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </form>
    </AppModal>
  </div>
</template>

<style scoped>
.advisor-entry { margin-top: var(--space-lg); text-decoration: none; }
.imprint-card {
  margin-bottom: var(--space-xl);
  background: linear-gradient(135deg, rgba(242, 140, 69, 0.16), rgba(36, 31, 26, 0.9));
}

.imprint-title {
  font-size: 17px;
  font-weight: 600;
  margin-bottom: var(--space-md);
}

.imprint-head {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  margin-bottom: var(--space-lg);
}

.avatar-lg {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: var(--color-primary-strong);
  color: var(--color-on-primary);
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 700;
}

.avatar-md {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: rgba(242, 140, 69, 0.24);
  color: var(--color-primary);
  font-weight: 700;
}

.imprint-name {
  font-size: 20px;
  line-height: 28px;
}

.imprint-sub {
  margin: 2px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.imprint-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-md);
}

.imprint-item {
  background: rgba(23, 19, 15, 0.5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.imprint-num {
  font-family: var(--font-heading);
  font-size: 26px;
  font-weight: 700;
  color: var(--color-primary);
}

.imprint-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.imprint-date {
  margin: var(--space-md) 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
}

.milestone-progress {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

.section {
  margin-bottom: var(--space-xl);
}

.section-head {
  justify-content: space-between;
  margin-bottom: var(--space-md);
}

.section-title {
  font-size: 17px;
  font-weight: 600;
}

.baby-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
}

.baby-card.active {
  border-color: var(--color-primary-strong);
}

.baby-name {
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.baby-meta {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.baby-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-top: var(--space-md);
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

.form-error {
  margin: 0;
  color: var(--color-danger);
  font-size: 13px;
}

.form-actions {
  margin-top: var(--space-sm);
}

@media (min-width: 768px) {
  .imprint-grid {
    grid-template-columns: repeat(4, 1fr);
  }

  .baby-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
