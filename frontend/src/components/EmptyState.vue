<script setup lang="ts">
/**
 * @file: src/components/EmptyState.vue
 * @description: 通用空态组件：图标占位 + 提示文案 + 可选操作按钮。
 */
import { useSlots } from 'vue'

// 组件属性定义
defineProps<{
  /** 空态提示文案 */
  text?: string
}>()

// 插槽集合（用于可选的操作区）
const slots = useSlots()
</script>

<template>
  <div class="empty-state">
    <div class="icon" aria-hidden="true">🌱</div>
    <p class="text">{{ text ?? '这里还没有内容' }}</p>
    <!-- 可选操作区插槽 -->
    <slot v-if="slots.default"></slot>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-xxl) var(--space-lg);
  text-align: center;
}

.icon {
  font-size: 34px;
}

.text {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}
</style>
