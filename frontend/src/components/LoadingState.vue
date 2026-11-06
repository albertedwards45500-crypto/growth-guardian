<script setup lang="ts">
/**
 * @file: src/components/LoadingState.vue
 * @description: 通用加载态组件：旋转指示器 + 可选提示文案。
 */
// 可选的加载提示文案
withDefaults(defineProps<{ text?: string }>(), { text: '加载中…' })
</script>

<template>
  <div class="loading-state" role="status">
    <span class="spinner" aria-hidden="true"></span>
    <p class="text">{{ text }}</p>
  </div>
</template>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
  padding: var(--space-xxl) var(--space-lg);
  color: var(--color-text-secondary);
}

.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary-strong);
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}

.text {
  margin: 0;
  font-size: 13px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
