<script setup lang="ts">
/**
 * @file: src/components/AppModal.vue
 * @description: 通用模态框组件：遮罩点击关闭 + 具名插槽承载表单或详情。
 */
// 组件属性定义
defineProps<{
  /** 弹层标题 */
  title: string
}>()

// emit 事件定义
const emit = defineEmits<{
  /** 请求关闭弹层时触发 */
  (e: 'close'): void
}>()
</script>

<template>
  <Teleport to="body">
    <div class="modal-mask" @click.self="emit('close')">
      <div class="modal" role="dialog" :aria-label="title">
        <div class="modal-head">
          <h2 class="modal-title">{{ title }}</h2>
          <button class="close-btn" type="button" aria-label="关闭" @click="emit('close')">✕</button>
        </div>
        <slot />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-lg);
}

.modal-title {
  font-size: 17px;
  font-weight: 600;
  line-height: 24px;
}

.close-btn {
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}

.close-btn:hover {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.06);
}
</style>
