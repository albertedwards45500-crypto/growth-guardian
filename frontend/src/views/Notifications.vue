<script setup lang="ts">
/**
 * @file: src/views/Notifications.vue
 * @description: 通知中心页：分页通知列表、未读筛选、未读数角标、单条与全部已读。
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  getUnreadCount,
  listNotifications,
  markAllRead,
  markRead
} from '@/api/notifications'
import type { Notification } from '@/types/api'
import LoadingState from '@/components/LoadingState.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'

// 页面状态
const loading = ref(false)
const error = ref('')

// 通知列表与分页
const items = ref<Notification[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
// 仅看未读
const unreadOnly = ref(false)
// 未读数
const unreadCount = ref(0)

/** 总页数（至少 1 页） */
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

/**
 * 加载通知列表与未读数。
 *
 * @throws Error 网络错误时展示错误态
 */
async function loadAll(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [resp, countResp] = await Promise.all([
      listNotifications({ unread_only: unreadOnly.value, page: page.value, page_size: pageSize }),
      getUnreadCount()
    ])
    items.value = resp.items
    total.value = resp.total
    unreadCount.value = countResp.unread_count
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

/**
 * 翻页。
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
 * 将单条通知标记为已读。
 *
 * @param item: 目标通知
 * @throws Error 接口错误时静默忽略
 */
async function onMarkRead(item: Notification): Promise<void> {
  if (item.is_read) return
  try {
    const updated = await markRead(item.id)
    item.is_read = updated.is_read
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    // 未读筛选下标记后刷新列表（当前条目会消失）
    if (unreadOnly.value) loadAll()
  } catch {
    // 忽略标记失败
  }
}

/**
 * 全部标记为已读。
 *
 * @throws Error 接口错误时静默忽略
 */
async function onMarkAll(): Promise<void> {
  try {
    await markAllRead()
    unreadCount.value = 0
    await loadAll()
  } catch {
    // 忽略操作失败
  }
}

/**
 * 通知类型转中文文案与样式。
 *
 * @param type: 通知类型编码
 * @returns 文案
 */
function typeText(type: string): string {
  const map: Record<string, string> = {
    vaccine: '疫苗接种',
    growth: '成长提醒',
    diet: '饮食建议',
    system: '系统通知'
  }
  return map[type] ?? type
}

/**
 * 通知类型对应标签样式。
 *
 * @param type: 通知类型编码
 * @returns 样式类名
 */
function typeClass(type: string): string {
  const map: Record<string, string> = {
    vaccine: 'tag tag-blue',
    growth: 'tag',
    diet: 'tag tag-green',
    system: 'tag tag-yellow'
  }
  return map[type] ?? 'tag'
}

// 切换未读筛选时回到第一页重新加载
watch(unreadOnly, () => {
  page.value = 1
  loadAll()
})

// 组件挂载：加载列表
onMounted(loadAll)
</script>

<template>
  <div class="page">
    <div class="row head">
      <h1 class="page-title grow">通知中心</h1>
      <span v-if="unreadCount > 0" class="tag tag-red">{{ unreadCount }} 条未读</span>
      <button
        v-if="unreadCount > 0"
        class="btn btn-ghost btn-sm"
        type="button"
        @click="onMarkAll"
      >
        全部已读
      </button>
    </div>

    <div class="row filter-row">
      <label class="checkbox-label">
        <input v-model="unreadOnly" type="checkbox" />
        仅看未读
      </label>
    </div>

    <ErrorState v-if="error && !loading" :message="error" @retry="loadAll" />
    <LoadingState v-else-if="loading" text="正在加载通知…" />
    <EmptyState v-else-if="items.length === 0" :text="unreadOnly ? '没有未读通知啦' : '暂时没有通知'" />

    <ul v-else class="notif-list">
      <li
        v-for="item in items"
        :key="item.id"
        class="card notif-item"
        :class="{ unread: !item.is_read }"
      >
        <div class="row notif-top">
          <span :class="typeClass(item.notify_type)">{{ typeText(item.notify_type) }}</span>
          <span class="date tabular">{{ item.created_at.replace('T', ' ').slice(0, 16) }}</span>
        </div>
        <h3 class="notif-title">
          <i v-if="!item.is_read" class="unread-dot" aria-hidden="true" />
          {{ item.title }}
        </h3>
        <p class="notif-content">{{ item.content }}</p>
        <button v-if="!item.is_read" class="link-btn" type="button" @click="onMarkRead(item)">
          标记已读
        </button>
      </li>
    </ul>

    <div v-if="!loading && total > pageSize" class="pager">
      <button class="btn btn-ghost btn-sm" type="button" :disabled="page <= 1" @click="changePage(-1)">
        上一页
      </button>
      <span class="tabular">第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
      <button class="btn btn-ghost btn-sm" type="button" :disabled="page >= totalPages" @click="changePage(1)">
        下一页
      </button>
    </div>
  </div>
</template>

<style scoped>
.head {
  flex-wrap: wrap;
}

.head .page-title {
  flex: 1;
  margin-bottom: 0;
}

.head {
  margin-bottom: var(--space-md);
}

.filter-row {
  margin-bottom: var(--space-lg);
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: 14px;
  color: var(--color-text-secondary);
  cursor: pointer;
  min-height: 24px;
}

.checkbox-label input {
  width: 18px;
  height: 18px;
  accent-color: var(--color-primary-strong);
}

.notif-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.notif-item.unread {
  border-color: var(--color-primary-strong);
}

.notif-top {
  justify-content: space-between;
  margin-bottom: var(--space-sm);
}

.date {
  font-size: 12px;
  color: var(--color-text-muted);
}

.notif-title {
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--color-primary-strong);
  flex-shrink: 0;
}

.notif-content {
  margin: var(--space-xs) 0 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.link-btn {
  margin-top: var(--space-sm);
  background: transparent;
  border: none;
  color: var(--color-primary);
  font-size: 13px;
  cursor: pointer;
  padding: 0;
}

.link-btn:hover {
  text-decoration: underline;
}
</style>
