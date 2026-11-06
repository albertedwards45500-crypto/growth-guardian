<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { AdvisorAnswer, AdvisorSource } from '@/types/advisor'
import AdvisorCitations from './AdvisorCitations.vue'

const props = defineProps<{ answer: AdvisorAnswer; question: string; babyName: string }>()
const sourceOpen = ref(false)
const prefix = computed(() => `advisor-source-${props.answer.request_id}`)
const levelText = computed(() => ({
  normal: '记录整理完成', caution: '有信息需要核实', urgent: '请尽快联系医护人员', emergency: '请立即寻求急救帮助'
})[props.answer.safety_level])
const methodText = computed(() => ({ rules: '按记录整理', agent: '智能整理', agent_rag: '智能整理 · 含知识摘录' })[props.answer.generation_mode])
const urgent = computed(() => ['urgent', 'emergency'].includes(props.answer.safety_level))

function publicUrl(source: AdvisorSource): string | null {
  if (!source.url) return null
  try {
    const url = new URL(source.url)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

async function revealSource(index: number): Promise<void> {
  sourceOpen.value = true
  await nextTick()
  document.getElementById(`${prefix.value}-${index}`)?.focus()
}
</script>

<template>
  <article class="advisor-result" aria-labelledby="answer-title">
    <header class="answer-header">
      <div><p class="answer-caption">{{ babyName }}的记录回顾 · 截至 {{ answer.as_of }}</p><h2 id="answer-title">本次整理</h2></div>
      <span class="method-label">{{ methodText }}</span>
    </header>
    <p class="asked-question">{{ question }}</p>
    <p v-if="answer.agent_status === 'failed' || answer.agent_status === 'unavailable'" class="fallback-notice" role="status">
      智能整理暂不可用，以下为已录入记录的整理结果。
    </p>

    <section class="answer-summary" :class="answer.safety_level" :role="urgent ? 'alert' : undefined">
      <p class="level-label">{{ levelText }}</p><p class="summary-text">{{ answer.summary }}</p>
      <a v-if="answer.safety_level === 'emergency'" class="emergency-call" href="tel:120">拨打 120</a>
    </section>

    <section v-if="answer.observations.length" class="answer-section">
      <h3>记录里看到的变化</h3>
      <ul class="fact-list"><li v-for="(item, index) in answer.observations" :key="index">{{ item.text }}
        <AdvisorCitations :ids="item.evidence_ids" :sources="answer.sources" :prefix="prefix" @reveal="revealSource" />
      </li></ul>
    </section>

    <section v-if="answer.recipe_candidates.length" class="answer-section">
      <h3>适龄辅食候选</h3>
      <p class="section-note">食用前请核对实际配料与交叉接触情况。</p>
      <div class="recipe-list"><article v-for="recipe in answer.recipe_candidates" :key="recipe.recipe_id" class="recipe-candidate">
        <h4>{{ recipe.title }}<AdvisorCitations :ids="recipe.evidence_ids" :sources="answer.sources" :prefix="prefix" @reveal="revealSource" /></h4>
        <p>目录食材：{{ recipe.ingredients.join('、') }}</p>
        <p v-if="recipe.nutrition_tags.length" class="section-note">目录标签：{{ recipe.nutrition_tags.join('、') }}</p>
      </article></div>
    </section>

    <section v-if="answer.knowledge.length" class="answer-section">
      <h3>通用知识摘录</h3>
      <blockquote v-for="quote in answer.knowledge" :key="quote.evidence_id" class="knowledge-quote">
        <p>{{ quote.text }}</p><AdvisorCitations :ids="[quote.evidence_id]" :sources="answer.sources" :prefix="prefix" @reveal="revealSource" />
      </blockquote>
    </section>

    <section v-if="answer.recommendations.length" class="answer-section">
      <h3>{{ urgent ? '现在应做的事' : '接下来可以做什么' }}</h3>
      <ul class="fact-list"><li v-for="(item, index) in answer.recommendations" :key="index">{{ item.text }}
        <AdvisorCitations :ids="item.evidence_ids" :sources="answer.sources" :prefix="prefix" @reveal="revealSource" />
      </li></ul>
    </section>

    <section v-if="answer.risks.length" class="answer-section limitations">
      <h3>需要留意</h3><ul class="fact-list"><li v-for="item in answer.risks" :key="item">{{ item }}</li></ul>
    </section>
    <section v-if="answer.missing_information.length" class="answer-section">
      <h3>还需要核实的信息</h3><ul class="fact-list"><li v-for="item in answer.missing_information" :key="item">{{ item }}</li></ul>
    </section>

    <details v-if="answer.sources.length" class="source-section" :open="sourceOpen" @toggle="sourceOpen = ($event.target as HTMLDetailsElement).open">
      <summary>查看本次依据 <span>{{ answer.sources.length }}条</span></summary>
      <ol v-if="sourceOpen" class="source-list">
        <li v-for="(source, index) in answer.sources" :id="`${prefix}-${index}`" :key="source.id" tabindex="-1">
          <a v-if="publicUrl(source)" :href="publicUrl(source)!" target="_blank" rel="noopener noreferrer">{{ source.label }} ↗</a>
          <span v-else>{{ source.label }}</span>
          <small v-if="source.as_of">记录日期 {{ source.as_of }}</small>
          <small v-if="source.version">版本 {{ source.version }}</small>
          <small v-if="source.reviewed_on">审核日期 {{ source.reviewed_on }}</small>
        </li>
      </ol>
    </details>
    <footer class="answer-footer"><p>{{ answer.disclaimer }}</p><span>本次编号 {{ answer.request_id }}</span></footer>
  </article>
</template>

<style scoped>
.advisor-result { min-width: 0; padding: 28px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.answer-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.answer-caption { color: var(--color-text-secondary); font-size: 12px; margin: 0 0 8px; }
.answer-header h2 { font-size: 24px; line-height: 1.4; }
.method-label { color: var(--color-secondary); font-size: 12px; white-space: nowrap; }
.asked-question { margin: 20px 0; padding-left: 14px; border-left: 2px solid var(--color-border-strong); overflow-wrap: anywhere; color: var(--color-text-secondary); white-space: pre-wrap; }
.fallback-notice { color: var(--color-tertiary); font-size: 13px; }
.answer-summary { padding: 18px 20px; border-left: 3px solid var(--color-secondary); background: var(--color-surface-low); border-radius: 0 var(--radius-md) var(--radius-md) 0; }
.answer-summary.caution { border-left-color: var(--color-tertiary); }
.answer-summary.urgent, .answer-summary.emergency { border: 1px solid var(--color-danger); border-left-width: 4px; }
.level-label { color: var(--color-secondary); font-size: 12px; font-weight: 700; margin: 0 0 8px; }
.caution .level-label { color: var(--color-tertiary); }
.urgent .level-label, .emergency .level-label { color: var(--color-primary); }
.summary-text { margin: 0; line-height: 1.8; overflow-wrap: anywhere; }
.emergency-call { display: inline-block; background: var(--color-primary); color: var(--color-on-primary); margin-top: 14px; padding: 10px 20px; border-radius: var(--radius-sm); font-weight: 700; text-decoration: none; }
.answer-section { margin-top: 26px; }
.answer-section h3 { font-size: 15px; margin-bottom: 12px; }
.fact-list { margin: 0; padding-left: 20px; }
.fact-list li { padding: 0 0 10px 3px; line-height: 1.8; overflow-wrap: anywhere; }
.fact-list li::marker { color: var(--color-primary); }
.section-note { font-size: 12px; color: var(--color-text-secondary); margin: 6px 0; }
.recipe-list { display: grid; gap: 10px; }
.recipe-candidate { padding: 14px 16px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.recipe-candidate h4 { margin: 0; font-size: 14px; }
.recipe-candidate p { margin-bottom: 0; font-size: 13px; overflow-wrap: anywhere; }
.knowledge-quote { margin: 12px 0; padding: 14px 18px; background: var(--color-surface-low); border-left: 2px solid var(--color-secondary); }
.knowledge-quote p { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0 0 8px; line-height: 1.8; }
.limitations { color: var(--color-text-secondary); }
.source-section { margin-top: 26px; border-top: 1px solid var(--color-border); padding-top: 18px; font-size: 13px; }
.source-section summary { cursor: pointer; color: var(--color-primary); padding: 4px 0; }
.source-section summary span { color: var(--color-text-secondary); margin-left: 6px; }
.source-list { padding-left: 24px; }
.source-list li { margin: 10px 0; padding: 5px; overflow-wrap: anywhere; }
.source-list a { color: var(--color-primary); }
.source-list small { display: block; color: var(--color-text-secondary); }
.answer-footer { margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--color-border); color: var(--color-text-secondary); font-size: 12px; }
.answer-footer p { margin: 0 0 6px; }
.answer-footer span { font-size: 11px; overflow-wrap: anywhere; }
a:focus-visible, summary:focus-visible, li:focus { outline: 2px solid var(--color-primary); outline-offset: 3px; }
@media (max-width: 600px) { .advisor-result { padding: 18px; } .answer-header { flex-direction: column; gap: 8px; } .answer-summary { padding: 14px; } }
</style>
