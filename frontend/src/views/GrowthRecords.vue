<script setup lang="ts">
/**
 * @file: src/views/GrowthRecords.vue
 * @description: 成长记录页：测量记录列表与新增、SVG 生长曲线（含 WHO 参考线）、里程碑管理。
 */
import { onMounted, reactive, ref } from 'vue'
import { useBabyStore } from '@/stores/baby'
import {
  createGrowthRecord,
  deleteGrowthRecord,
  getGrowthCurve,
  listGrowthRecords,
  listMilestones,
  createMilestone,
  deleteMilestone
} from '@/api/growth'
import type { GrowthCurve, GrowthRecord, Milestone } from '@/types/api'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import GrowthCurveView from '@/components/GrowthCurve.vue'
import AppModal from '@/components/AppModal.vue'

// 宝宝 store
const babyStore = useBabyStore()

// 页面状态
const loading = ref(false)
const error = ref('')

// 生长记录列表
const records = ref<GrowthRecord[]>([])
// 曲线数据
const curve = ref<GrowthCurve | null>(null)
// 曲线维度
const curveMetric = ref<'height' | 'weight'>('height')

// 新增记录弹层
const showForm = ref(false)
const saving = ref(false)
const formError = ref('')
// 测量表单（空字符串表示未填写）
const form = reactive<{
  record_date: string
  weight_kg: string
  height_cm: string
  head_circumference_cm: string
  note: string
}>({ record_date: new Date().toISOString().slice(0, 10), weight_kg: '', height_cm: '', head_circumference_cm: '', note: '' })

// 里程碑
const milestones = ref<Milestone[]>([])
const showMilestoneForm = ref(false)
const milestoneSaving = ref(false)
const milestoneError = ref('')
const milestoneForm = reactive<{ milestone_type: string; name: string; achieved_at: string; note: string }>({
  milestone_type: 'motor',
  name: '',
  achieved_at: new Date().toISOString().slice(0, 10),
  note: ''
})

// 里程碑类型选项
const milestoneTypes = [
  { value: 'motor', label: '大运动' },
  { value: 'fine', label: '精细动作' },
  { value: 'language', label: '语言' },
  { value: 'social', label: '社交认知' }
]

// 今天日期字符串（日期上限）
const todayStr = new Date().toISOString().slice(0, 10)

/**
 * 拉取记录、曲线与里程碑。
 *
 * @throws Error 网络错误时展示错误态
 */
async function loadAll(): Promise<void> {
  const babyId = babyStore.currentBabyId
  if (babyId === null) {
    records.value = []
    curve.value = null
    milestones.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [r, c, m] = await Promise.all([
      listGrowthRecords(babyId),
      getGrowthCurve(babyId),
      listMilestones(babyId)
    ])
    records.value = r
    curve.value = c
    milestones.value = m
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

/**
 * 打开新增测量弹层。
 */
function openForm(): void {
  form.record_date = new Date().toISOString().slice(0, 10)
  form.weight_kg = ''
  form.height_cm = ''
  form.head_circumference_cm = ''
  form.note = ''
  formError.value = ''
  showForm.value = true
}

/**
 * 校验并保存测量记录。
 *
 * @throws Error 三项均未填写（40001）或接口校验失败时展示错误
 */
async function onSaveRecord(): Promise<void> {
  if (saving.value) return
  const babyId = babyStore.currentBabyId
  if (babyId === null) return
  const weight = form.weight_kg === '' ? null : Number(form.weight_kg)
  const height = form.height_cm === '' ? null : Number(form.height_cm)
  const head = form.head_circumference_cm === '' ? null : Number(form.head_circumference_cm)
  if (weight === null && height === null && head === null) {
    formError.value = '体重、身高、头围至少填写一项'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    await createGrowthRecord(babyId, {
      record_date: form.record_date,
      weight_kg: weight,
      height_cm: height,
      head_circumference_cm: head,
      note: form.note.trim() || null
    })
    showForm.value = false
    await loadAll()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

/**
 * 删除测量记录。
 *
 * @param record: 目标记录
 * @throws Error 接口错误时静默忽略
 */
async function onDeleteRecord(record: GrowthRecord): Promise<void> {
  if (!window.confirm('确定删除这条测量记录吗？')) return
  try {
    await deleteGrowthRecord(record.id)
    await loadAll()
  } catch {
    // 忽略删除失败
  }
}

/**
 * 打开新增里程碑弹层。
 */
function openMilestoneForm(): void {
  milestoneForm.milestone_type = 'motor'
  milestoneForm.name = ''
  milestoneForm.achieved_at = new Date().toISOString().slice(0, 10)
  milestoneForm.note = ''
  milestoneError.value = ''
  showMilestoneForm.value = true
}

/**
 * 校验并保存里程碑。
 *
 * @throws Error 接口校验失败时展示错误
 */
async function onSaveMilestone(): Promise<void> {
  if (milestoneSaving.value) return
  const babyId = babyStore.currentBabyId
  if (babyId === null) return
  if (!milestoneForm.name.trim()) {
    milestoneError.value = '请填写里程碑名称'
    return
  }
  milestoneSaving.value = true
  milestoneError.value = ''
  try {
    await createMilestone(babyId, {
      milestone_type: milestoneForm.milestone_type,
      name: milestoneForm.name.trim(),
      achieved_at: milestoneForm.achieved_at,
      note: milestoneForm.note.trim() || null
    })
    showMilestoneForm.value = false
    await loadAll()
  } catch (err) {
    milestoneError.value = err instanceof Error ? err.message : '保存失败，请稍后重试'
  } finally {
    milestoneSaving.value = false
  }
}

/**
 * 删除里程碑。
 *
 * @param milestone: 目标里程碑
 * @throws Error 接口错误时静默忽略
 */
async function onDeleteMilestone(milestone: Milestone): Promise<void> {
  if (!window.confirm(`确定删除里程碑「${milestone.name}」吗？`)) return
  try {
    await deleteMilestone(milestone.id)
    await loadAll()
  } catch {
    // 忽略删除失败
  }
}

/**
 * 里程碑类型编码转中文文案。
 *
 * @param type: 类型编码
 * @returns 中文文案
 */
function milestoneTypeText(type: string): string {
  return milestoneTypes.find((t) => t.value === type)?.label ?? type
}

// 组件挂载：加载数据（列表经 store 缓存去重）
onMounted(async () => {
  await babyStore.ensureLoaded().catch(() => undefined)
  await loadAll()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">成长记录</h1>

    <EmptyState
      v-if="!loading && !error && babyStore.babies.length === 0"
      text="请先在「宝宝概览」创建宝宝档案"
    />

    <template v-else>
      <ErrorState v-if="error && !loading" :message="error" @retry="loadAll" />
      <LoadingState v-else-if="loading" text="正在加载成长数据…" />

      <template v-else>
        <!-- 生长曲线 -->
        <section class="card curve-card">
          <div class="row section-head">
            <h2 class="section-title">生长曲线</h2>
            <div class="metric-tabs">
              <button
                class="metric-tab"
                :class="{ active: curveMetric === 'height' }"
                type="button"
                @click="curveMetric = 'height'"
              >
                身长
              </button>
              <button
                class="metric-tab"
                :class="{ active: curveMetric === 'weight' }"
                type="button"
                @click="curveMetric = 'weight'"
              >
                体重
              </button>
            </div>
          </div>
          <GrowthCurveView v-if="curve" :curve="curve" :metric="curveMetric" />
          <EmptyState v-else text="暂无测量数据，添加一条记录后即可生成曲线" />
        </section>

        <!-- 测量记录 -->
        <section class="section">
          <div class="row section-head">
            <h2 class="section-title">测量记录</h2>
            <button class="btn btn-primary btn-sm" type="button" @click="openForm">+ 新增测量</button>
          </div>

          <EmptyState v-if="records.length === 0" text="还没有测量记录" />
          <ul v-else class="record-list">
            <li v-for="r in records" :key="r.id" class="card record-item">
              <div class="record-date">
                <span class="tabular date">{{ r.record_date }}</span>
                <button class="link-danger" type="button" @click="onDeleteRecord(r)">删除</button>
              </div>
              <div class="record-metrics">
                <span v-if="r.weight_kg !== null" class="tag tag-green">体重 {{ r.weight_kg }} kg</span>
                <span v-if="r.height_cm !== null" class="tag">身长 {{ r.height_cm }} cm</span>
                <span v-if="r.head_circumference_cm !== null" class="tag tag-blue">
                  头围 {{ r.head_circumference_cm }} cm
                </span>
              </div>
              <p v-if="r.note" class="record-note">{{ r.note }}</p>
            </li>
          </ul>
        </section>

        <!-- 里程碑 -->
        <section class="section">
          <div class="row section-head">
            <h2 class="section-title">成长里程碑</h2>
            <button class="btn btn-ghost btn-sm" type="button" @click="openMilestoneForm">
              + 记录里程碑
            </button>
          </div>

          <EmptyState v-if="milestones.length === 0" text="记录宝宝第一次翻身、第一次叫妈妈…" />
          <ul v-else class="record-list">
            <li v-for="m in milestones" :key="m.id" class="card record-item">
              <div class="record-date">
                <span class="tag tag-purple">{{ milestoneTypeText(m.milestone_type) }}</span>
                <span class="tabular date">{{ m.achieved_at }}</span>
                <button class="link-danger" type="button" @click="onDeleteMilestone(m)">删除</button>
              </div>
              <h3 class="milestone-name">{{ m.name }}</h3>
              <p v-if="m.note" class="record-note">{{ m.note }}</p>
            </li>
          </ul>
        </section>
      </template>
    </template>

    <!-- 新增测量弹层 -->
    <AppModal v-if="showForm" title="新增测量记录" @close="showForm = false">
      <form class="form" novalidate @submit.prevent="onSaveRecord">
        <div class="field">
          <label class="label" for="g-date">测量日期</label>
          <input id="g-date" v-model="form.record_date" class="input" type="date" :max="todayStr" />
        </div>
        <div class="field-grid">
          <div class="field">
            <label class="label" for="g-weight">体重 (kg)</label>
            <input id="g-weight" v-model="form.weight_kg" class="input" type="number" step="0.01" min="0" max="50" placeholder="选填" />
          </div>
          <div class="field">
            <label class="label" for="g-height">身长 (cm)</label>
            <input id="g-height" v-model="form.height_cm" class="input" type="number" step="0.1" min="0" max="150" placeholder="选填" />
          </div>
          <div class="field">
            <label class="label" for="g-head">头围 (cm)</label>
            <input id="g-head" v-model="form.head_circumference_cm" class="input" type="number" step="0.1" min="0" max="100" placeholder="选填" />
          </div>
        </div>
        <div class="field">
          <label class="label" for="g-note">备注（选填）</label>
          <textarea id="g-note" v-model="form.note" class="textarea" rows="2" maxlength="500" placeholder="体检情况、注意事项…" />
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

    <!-- 新增里程碑弹层 -->
    <AppModal v-if="showMilestoneForm" title="记录里程碑" @close="showMilestoneForm = false">
      <form class="form" novalidate @submit.prevent="onSaveMilestone">
        <div class="field">
          <label class="label" for="m-type">类型</label>
          <select id="m-type" v-model="milestoneForm.milestone_type" class="select">
            <option v-for="t in milestoneTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </div>
        <div class="field">
          <label class="label" for="m-name">名称</label>
          <input id="m-name" v-model="milestoneForm.name" class="input" type="text" maxlength="50" placeholder="如：第一次翻身" />
        </div>
        <div class="field">
          <label class="label" for="m-date">达成日期</label>
          <input id="m-date" v-model="milestoneForm.achieved_at" class="input" type="date" :max="todayStr" />
        </div>
        <div class="field">
          <label class="label" for="m-note">备注（选填）</label>
          <textarea id="m-note" v-model="milestoneForm.note" class="textarea" rows="2" maxlength="500" />
        </div>
        <p v-if="milestoneError" class="form-error" role="alert">{{ milestoneError }}</p>
        <div class="row form-actions">
          <button class="btn btn-ghost grow" type="button" @click="showMilestoneForm = false">取消</button>
          <button class="btn btn-primary grow" type="submit" :disabled="milestoneSaving">
            {{ milestoneSaving ? '保存中…' : '保存' }}
          </button>
        </div>
      </form>
    </AppModal>
  </div>
</template>

<style scoped>
.curve-card {
  margin-bottom: var(--space-xl);
}

.metric-tabs {
  display: flex;
  gap: 4px;
  background: var(--color-surface-high);
  border-radius: var(--radius-sm);
  padding: 3px;
}

.metric-tab {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 5px 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.metric-tab.active {
  background: var(--color-primary-strong);
  color: var(--color-on-primary);
  font-weight: 600;
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

.record-date {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}

.date {
  font-size: 13px;
  color: var(--color-text-secondary);
  flex: 1;
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

.record-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.milestone-name {
  font-size: 15px;
  margin-top: var(--space-xs);
}

.record-note {
  margin: var(--space-sm) 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
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

.field-grid {
  display: grid;
  grid-template-columns: 1fr;
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
  .field-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
