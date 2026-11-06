<script setup lang="ts">
/**
 * @file: src/components/ErrorState.vue
 * @description: 通用错误态组件：错误提示 + 重试按钮。
 */
// 组件属性定义
defineProps<{
  /** 错误提示文案 */
  message?: string
}>()

// emit 事件定义
const emit = defineEmits<{
  /** 点击重试按钮时触发 */
  (e: 'retry'): void
}>()
</script>

<template>
  <div class="error-state" role="alert">
    <div class="icon" aria-hidden="true">⚠️</div>
    <p class="text">{{ message ?? '加载失败，请稍后重试' }}</p>
    <button class="btn btn-ghost btn-sm" type="button" @click="emit('retry')">重试</button>
  </div>
</template>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-xxl) var(--space-lg);
  text-align: center;
}

.icon {
  font-size: 30px;
}

.text {
  margin: 0;
  color: var(--color-danger);
  font-size: 14px;
}
</style>
