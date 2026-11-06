<script setup lang="ts">
import { computed } from 'vue'
import type { AdvisorSource } from '@/types/advisor'

const props = defineProps<{ ids: string[]; sources: AdvisorSource[]; prefix: string }>()
const emit = defineEmits<{ reveal: [index: number] }>()
const references = computed(() => [...new Set(props.ids)].map(id => props.sources.findIndex(source => source.id === id)).filter(index => index >= 0))
</script>

<template>
  <span v-if="references.length" class="citations" aria-label="本条内容的依据">
    <a v-for="index in references.slice(0, 3)" :key="index" :href="`#${prefix}-${index}`"
       :aria-label="`查看依据${index + 1}`" @click.prevent="emit('reveal', index)">[{{ index + 1 }}]</a>
    <a v-if="references.length > 3" :href="`#${prefix}-${references[3]}`" @click.prevent="emit('reveal', references[3])">另{{ references.length - 3 }}条</a>
  </span>
</template>

<style scoped>
.citations { display: inline-flex; gap: 6px; margin-left: 8px; font-size: 12px; }
.citations a { color: var(--color-primary); text-decoration: none; }
.citations a:hover { text-decoration: underline; }
.citations a:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 3px; }
</style>
