<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { askAdvisor, getAdvisorStatus } from '@/api/advisor'
import { useBabyStore } from '@/stores/baby'
import type { AdvisorAnswer, AdvisorCapabilities, AdvisorIntent, AdvisorRequest } from '@/types/advisor'
import AdvisorResult from '@/components/AdvisorResult.vue'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'

const babyStore = useBabyStore()
const pageLoading = ref(!babyStore.loaded)
const pageError = ref('')
const status = ref<AdvisorCapabilities | null>(null)
const statusError = ref(false)
const question = ref('')
const intent = ref<AdvisorIntent | ''>('')
const asOf = ref('')
const days = ref(7)
const formError = ref('')
const requestError = ref('')
const notice = ref('')
const asking = ref(false)
const answer = ref<AdvisorAnswer | null>(null)
const submitted = ref({ question: '', babyName: '' })
const questionField = ref<HTMLTextAreaElement>()
const resultArea = ref<HTMLElement>()
let contextVersion = 0
let requestVersion = 0
let statusController: AbortController | undefined
let requestController: AbortController | undefined

const today = computed(() => status.value?.today ?? new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
}).format(new Date()))
const presets: Array<{ intent: AdvisorIntent; label: string; question: string }> = [
  { intent: 'growth_review', label: '看看成长变化', question: '回顾最近的身高和体重记录，有哪些数值变化？' },
  { intent: 'diet_review', label: '整理最近的饮食', question: '整理最近7天的饮食记录，哪些信息还需要补充？' },
  { intent: 'recipe_recommendation', label: '找适龄辅食候选', question: '按月龄和已登记过敏史筛选辅食食谱候选。' },
  { intent: 'feeding_knowledge', label: '查阅喂养知识', question: '辅食添加有哪些可以参考的通用知识？' }
]
const knowledgeLabel = computed(() => {
  if (!status.value) return statusError.value ? '知识资料状态暂不可读' : '正在读取功能状态'
  return { disabled: '知识资料暂未启用', unconfigured: '知识资料尚待配置', configured: '知识资料检索已配置' }[status.value.knowledge]
})
const agentLabel = computed(() => status.value ? {
  disabled: '按记录整理', unconfigured: '智能整理尚待配置', configured: '智能整理已配置'
}[status.value.agent] : '')

function stopRequest(): void {
  requestVersion++
  requestController?.abort()
  requestController = undefined
  asking.value = false
}

async function loadStatus(): Promise<void> {
  const babyId = babyStore.currentBaby?.id
  if (!babyId) return
  const version = contextVersion
  statusController?.abort()
  const controller = new AbortController()
  statusController = controller
  statusError.value = false
  try {
    const result = await getAdvisorStatus(babyId, controller.signal)
    if (version === contextVersion && !controller.signal.aborted) status.value = result
  } catch {
    if (version === contextVersion && !controller.signal.aborted) statusError.value = true
  }
}

watch(() => babyStore.currentBaby?.id, () => {
  contextVersion++
  stopRequest()
  statusController?.abort()
  status.value = null
  statusError.value = false
  answer.value = null
  question.value = ''
  intent.value = ''
  asOf.value = ''
  days.value = 7
  submitted.value = { question: '', babyName: '' }
  formError.value = requestError.value = notice.value = ''
  void loadStatus()
}, { immediate: true, flush: 'sync' })

async function loadPage(): Promise<void> {
  pageLoading.value = true
  pageError.value = ''
  try { await babyStore.ensureLoaded() }
  catch { pageError.value = '宝宝档案加载失败，请重试后再提问。' }
  finally { pageLoading.value = false }
}

async function choosePreset(preset: typeof presets[number]): Promise<void> {
  intent.value = preset.intent
  question.value = preset.question
  if (preset.intent === 'diet_review') days.value = 7
  formError.value = ''
  await nextTick()
  questionField.value?.focus()
}

async function submit(): Promise<void> {
  const baby = babyStore.currentBaby
  if (!baby || asking.value) return
  formError.value = ''
  const text = question.value.trim()
  if (text.length < 2 || text.length > 500) { formError.value = '请输入2至500字的问题。'; return }
  if (asOf.value && (asOf.value < baby.birth_date || asOf.value > today.value)) {
    formError.value = '回顾日期应在宝宝出生日期与今天之间。'; return
  }
  if ((!intent.value || intent.value === 'diet_review') && (!Number.isInteger(days.value) || days.value < 1 || days.value > 31)) {
    formError.value = '饮食回顾天数应为1至31的整数。'; return
  }
  const payload: AdvisorRequest = { question: text }
  if (intent.value) payload.intent = intent.value
  if (asOf.value) payload.as_of = asOf.value
  if (!intent.value || intent.value === 'diet_review') payload.days = days.value
  const version = ++requestVersion
  const controller = new AbortController()
  requestController = controller
  asking.value = true
  answer.value = null
  requestError.value = notice.value = ''
  submitted.value = { question: text, babyName: baby.name }
  try {
    const result = await askAdvisor(baby.id, payload, controller.signal)
    if (version === requestVersion && !controller.signal.aborted && babyStore.currentBaby?.id === baby.id) answer.value = result
  } catch (error) {
    if (version === requestVersion && !controller.signal.aborted) requestError.value = error instanceof Error ? error.message : '整理失败，请稍后重试。'
  } finally {
    if (version === requestVersion) {
      asking.value = false
      requestController = undefined
      await nextTick()
      if (version === requestVersion && !controller.signal.aborted) {
        resultArea.value?.focus({ preventScroll: true })
        resultArea.value?.scrollIntoView?.({ block: 'start' })
      }
    }
  }
}

function cancelWaiting(): void {
  stopRequest()
  notice.value = '已停止等待。刚才的请求可能仍在处理，请稍后再发起。'
}

onMounted(loadPage)
onBeforeUnmount(() => { contextVersion++; stopRequest(); statusController?.abort() })
</script>

<template>
  <div class="page advisor-page">
    <header class="advisor-heading"><div><p class="page-kicker">从日常记录出发</p><h1 class="page-title">成长顾问</h1>
      <p class="page-description">回顾成长与喂养记录，把变化和待核实的信息整理清楚。</p></div>
      <RouterLink class="records-link" :to="{ name: 'overview' }">查看宝宝档案 ↗</RouterLink>
    </header>

    <LoadingState v-if="pageLoading" text="正在读取宝宝档案…" />
    <ErrorState v-else-if="pageError" :message="pageError" @retry="loadPage" />
    <EmptyState v-else-if="!babyStore.currentBaby" text="先创建宝宝档案，再整理成长与饮食记录。">
      <RouterLink class="btn btn-primary" :to="{ name: 'overview' }">创建宝宝档案</RouterLink>
    </EmptyState>
    <div v-else class="advisor-workspace">
      <section class="composer card" aria-labelledby="composer-title">
        <div class="baby-context"><span class="baby-initial" aria-hidden="true">{{ babyStore.currentBaby.name.slice(0, 1) }}</span>
          <div><span class="context-label">当前整理对象</span><strong>{{ babyStore.currentBaby.name }}</strong></div></div>
        <h2 id="composer-title">想了解什么？</h2>
        <div class="preset-grid"><button v-for="preset in presets" :key="preset.intent" type="button" class="preset-button" :disabled="asking" @click="choosePreset(preset)">{{ preset.label }} <span aria-hidden="true">↗</span></button></div>

        <form novalidate @submit.prevent="submit">
          <div class="field"><label for="advisor-question" class="label">你的问题</label>
            <textarea id="advisor-question" ref="questionField" v-model="question" class="textarea" rows="4" maxlength="500" :disabled="asking" placeholder="例如：回顾最近的体重记录，有哪些变化？" aria-describedby="question-help" />
            <div id="question-help" class="question-help"><span>每次提问独立整理</span><span>{{ question.length }}/500</span></div></div>
          <div class="field"><label class="label" for="advisor-intent">整理内容</label><select id="advisor-intent" v-model="intent" class="select" :disabled="asking">
            <option value="">按问题识别</option><option value="growth_review">成长记录回顾</option><option value="diet_review">饮食记录回顾</option><option value="recipe_recommendation">适龄辅食候选</option><option value="feeding_knowledge">通用喂养知识</option>
          </select></div>
          <div class="filter-row"><div class="field"><label class="label" for="advisor-date">回顾截至</label><input id="advisor-date" v-model="asOf" class="input" type="date" :min="babyStore.currentBaby.birth_date" :max="today" :disabled="asking" /><small>留空为今天</small></div>
            <div v-if="!intent || intent === 'diet_review'" class="field"><label class="label" for="advisor-days">饮食回顾天数</label><input id="advisor-days" v-model.number="days" class="input" type="number" min="1" max="31" step="1" :disabled="asking" /><small>含截至当天，最多31天</small></div></div>
          <p v-if="formError" class="form-message" role="alert">{{ formError }}</p>
          <p class="sharing-note">启用智能整理时，问题、月龄和所需记录摘要会发送至模型服务。请勿填写姓名、电话等无关个人信息。</p>
          <button type="submit" class="btn btn-primary submit-button" :disabled="asking">{{ asking ? '正在整理…' : '开始整理' }} <span v-if="!asking" aria-hidden="true">→</span></button>
          <button v-if="asking" type="button" class="cancel-button" @click="cancelWaiting">停止等待</button>
        </form>
        <div class="feature-status"><span class="status-dot" aria-hidden="true"></span><span>{{ agentLabel }}{{ agentLabel ? ' · ' : '' }}{{ knowledgeLabel }}</span><button v-if="statusError" type="button" @click="loadStatus">重试</button></div>
        <p class="scope-note">仅整理记录与筛选候选，不能替代儿科诊疗。</p>
      </section>

      <section ref="resultArea" class="answer-area" aria-label="顾问整理结果" :aria-busy="asking" tabindex="-1">
        <div v-if="asking" class="waiting-panel card" role="status"><span class="waiting-mark" aria-hidden="true">…</span><h2>正在核对记录与依据</h2><p>只整理当前宝宝的数据，请稍候。复杂问题可能需要更长时间。</p></div>
        <div v-else-if="requestError" class="result-error card" role="alert"><h2>本次整理没有完成</h2><p>{{ requestError }}</p><p>问题已保留，请检查连接后点击“开始整理”重试。</p></div>
        <div v-else-if="notice" class="result-error card" role="status"><h2>已停止等待</h2><p>{{ notice }}</p></div>
        <AdvisorResult v-else-if="answer" :key="answer.request_id" :answer="answer" :question="submitted.question" :baby-name="submitted.babyName" />
        <div v-else class="answer-intro card"><div class="paper-lines" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
          <p class="intro-eyebrow">一次提问，一份有依据的回顾</p><h2>从一条记录，<br />看清下一步。</h2><p>选择一个示例问题，或写下你想了解的事。结果会列出记录依据、信息缺口和需要留意的地方。</p>
          <div class="intro-links"><RouterLink :to="{ name: 'growth' }">补充成长记录 ↗</RouterLink><RouterLink :to="{ name: 'diet' }">核对饮食与过敏史 ↗</RouterLink></div>
          <p v-if="status?.knowledge === 'disabled' || status?.knowledge === 'unconfigured'" class="knowledge-notice">喂养知识暂未启用。现在可以回顾记录、筛选适龄辅食候选。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.advisor-page { max-width: 1360px; }
.advisor-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 28px; }
.page-kicker { color: var(--color-primary); font-size: 12px; margin: 0 0 8px; }
.advisor-heading .page-title { margin-bottom: 10px; }
.page-description { color: var(--color-text-secondary); margin: 0; font-size: 14px; }
.records-link, .intro-links a { color: var(--color-primary); text-decoration: none; font-size: 13px; }
.records-link { flex-shrink: 0; }
.advisor-workspace { display: grid; grid-template-columns: minmax(280px, 360px) minmax(0, 1fr); gap: 24px; align-items: start; }
.composer { padding: 24px; }
.baby-context { display: flex; gap: 12px; align-items: center; margin-bottom: 28px; padding-bottom: 20px; border-bottom: 1px solid var(--color-border); }
.baby-initial { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; background: var(--color-primary-strong); color: var(--color-on-primary); font-family: var(--font-heading); font-weight: 700; font-size: 19px; }
.baby-context strong { display: block; overflow-wrap: anywhere; font-size: 17px; }
.context-label { font-size: 11px; color: var(--color-text-secondary); }
.composer h2 { font-size: 19px; margin-bottom: 16px; }
.preset-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 24px; }
.preset-button { display: flex; align-items: center; justify-content: space-between; gap: 4px; padding: 10px; border: 1px solid var(--color-border); background: var(--color-surface-low); color: var(--color-text-secondary); font: inherit; font-size: 12px; border-radius: var(--radius-sm); cursor: pointer; text-align: left; }
.preset-button span { color: var(--color-primary); }
.preset-button:hover:not(:disabled) { border-color: var(--color-primary); color: var(--color-text); }
.field { margin-bottom: 16px; min-width: 0; }
.field small { display: block; color: var(--color-text-secondary); font-size: 11px; margin-top: 5px; }
.textarea { resize: vertical; min-height: 120px; line-height: 1.6; }
.question-help { display: flex; justify-content: space-between; color: var(--color-text-secondary); font-size: 11px; margin-top: 5px; gap: 8px; }
.filter-row { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 12px; }
.input[type=date] { color-scheme: dark; min-width: 0; padding-left: 8px; padding-right: 8px; }
.sharing-note { font-size: 11px; line-height: 1.7; color: var(--color-text-secondary); margin: 2px 0 16px; }
.submit-button { width: 100%; justify-content: space-between; }
.cancel-button { display: block; margin: 14px auto 0; padding: 6px; font: inherit; font-size: 13px; background: transparent; border: 0; color: var(--color-primary); cursor: pointer; }
.feature-status { display: flex; gap: 7px; align-items: center; margin-top: 20px; color: var(--color-text-secondary); font-size: 11px; }
.status-dot { width: 5px; height: 5px; background: var(--color-text-muted); border-radius: 50%; flex-shrink: 0; }
.feature-status button { border: 0; background: transparent; font: inherit; color: var(--color-primary); cursor: pointer; }
.scope-note { font-size: 11px; color: var(--color-text-secondary); margin: 8px 0 0; }
.form-message { color: var(--color-primary); font-size: 13px; }
.answer-area { min-width: 0; scroll-margin-top: 24px; }
.answer-intro { padding: 40px; min-height: 490px; position: relative; overflow: hidden; }
.paper-lines { width: 80px; padding: 12px 0; border-top: 3px solid var(--color-primary-strong); margin-bottom: 36px; }
.paper-lines span { display: block; height: 1px; background: var(--color-border-strong); margin: 8px 0; }
.paper-lines span:nth-child(2) { width: 70%; }.paper-lines span:nth-child(4) { width: 45%; }
.intro-eyebrow { color: var(--color-primary); font-size: 12px; }
.answer-intro h2 { font-size: clamp(26px, 3vw, 38px); line-height: 1.5; letter-spacing: 1px; margin-bottom: 20px; }
.answer-intro > p:not(.intro-eyebrow):not(.knowledge-notice) { max-width: 410px; color: var(--color-text-secondary); font-size: 14px; line-height: 1.8; }
.intro-links { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 24px; }
.answer-intro .knowledge-notice { border-top: 1px solid var(--color-border); padding-top: 20px; margin-top: 30px; font-size: 12px; color: var(--color-text-secondary); line-height: 1.8; }
.waiting-panel, .result-error { padding: 36px; }
.waiting-panel h2, .result-error h2 { font-size: 20px; margin: 12px 0; }
.waiting-panel p, .result-error p { color: var(--color-text-secondary); font-size: 14px; line-height: 1.8; }
.waiting-mark { color: var(--color-primary); font-size: 36px; letter-spacing: 6px; }
a:focus-visible, button:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 4px; }
@media (max-width: 1050px) { .advisor-workspace { grid-template-columns: minmax(260px, 320px) minmax(0, 1fr); gap: 16px; } .composer { padding: 18px; } .answer-intro { padding: 28px; } }
@media (max-width: 900px) { .advisor-workspace { grid-template-columns: minmax(0, 1fr); } .advisor-heading { align-items: flex-start; } .answer-intro { min-height: auto; } .paper-lines { margin-bottom: 16px; } }
@media (max-width: 767px) { .answer-area { scroll-margin-top: 130px; } }
@media (max-width: 500px) { .advisor-heading { flex-direction: column; gap: 12px; } .advisor-heading .page-title { font-size: 26px; } .answer-intro, .waiting-panel, .result-error { padding: 24px; } .filter-row { grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); } }
</style>
