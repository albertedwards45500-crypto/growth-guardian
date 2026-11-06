<script setup lang="ts">
/**
 * @file: src/views/Layout.vue
 * @description: 主布局：桌面侧边导航（≥768px）+ 移动端顶栏导航，含宝宝切换、未读角标与用户退出。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useBabyStore } from '@/stores/baby'
import { getUnreadCount } from '@/api/notifications'

// 路由实例
const router = useRouter()
// 认证 store
const auth = useAuthStore()
// 宝宝 store
const babyStore = useBabyStore()

// 未读通知数
const unreadCount = ref(0)

// 主导航菜单定义
const navItems = [
  { name: 'overview', label: '宝宝概览', icon: '👶' },
  { name: 'growth', label: '成长记录', icon: '📈' },
  { name: 'diet', label: '饮食记录', icon: '🍽️' },
  { name: 'recipes', label: '食谱推荐', icon: '🥣' },
  { name: 'advisor', label: '成长顾问', icon: '💬' },
  { name: 'notifications', label: '通知中心', icon: '🔔' }
]

/**
 * 刷新未读通知数。
 *
 * @throws Error 未认证时静默忽略（由拦截器统一登出）
 */
async function refreshUnread(): Promise<void> {
  try {
    const resp = await getUnreadCount()
    unreadCount.value = resp.unread_count
  } catch {
    // 角标获取失败不阻塞主界面
  }
}

/**
 * 退出登录：清空状态并跳转登录页。
 */
function onLogout(): void {
  auth.logout()
  router.push({ name: 'login' })
}

// 组件挂载：加载宝宝档案与未读数（列表经 store 缓存去重，避免与页面重复请求）
onMounted(async () => {
  if (!auth.user) {
    auth.fetchUser().catch(() => undefined)
  }
  await babyStore.ensureLoaded().catch(() => undefined)
  await refreshUnread()
})

// 暴露刷新未读数方法（通知页读后角标联动）
defineExpose({ refreshUnread })
</script>

<template>
  <div class="layout">
    <!-- 桌面侧边栏 -->
    <aside class="sidebar">
      <div class="brand">🌱 成长宝</div>
      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          class="nav-item"
          :to="{ name: item.name }"
        >
          <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
          <span v-if="item.name === 'notifications' && unreadCount > 0" class="badge">
            {{ unreadCount > 99 ? '99+' : unreadCount }}
          </span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="baby-switcher" v-if="babyStore.babies.length > 1">
          <label class="label" for="baby-select">当前宝宝</label>
          <select
            id="baby-select"
            class="select"
            :value="babyStore.currentBabyId"
            @change="babyStore.setCurrentBaby(Number(($event.target as HTMLSelectElement).value))"
          >
            <option v-for="b in babyStore.babies" :key="b.id" :value="b.id">
              {{ b.name }}{{ b.is_default ? '（默认）' : '' }}
            </option>
          </select>
        </div>
        <div class="user-row">
          <span class="avatar" aria-hidden="true">{{ (auth.user?.nickname ?? '家长').slice(0, 1) }}</span>
          <span class="nickname">{{ auth.user?.nickname ?? '家长' }}</span>
          <button class="btn btn-ghost btn-sm" type="button" @click="onLogout">退出</button>
        </div>
      </div>
    </aside>

    <!-- 内容区 -->
    <div class="content">
      <!-- 移动端顶栏 -->
      <header class="topbar">
        <div class="topbar-row">
          <div class="brand-sm">🌱 成长宝</div>
          <select
            v-if="babyStore.babies.length > 1"
            class="select baby-select-sm"
            :value="babyStore.currentBabyId"
            aria-label="切换宝宝"
            @change="babyStore.setCurrentBaby(Number(($event.target as HTMLSelectElement).value))"
          >
            <option v-for="b in babyStore.babies" :key="b.id" :value="b.id">{{ b.name }}</option>
          </select>
          <button class="btn btn-ghost btn-sm" type="button" @click="onLogout">退出</button>
        </div>
        <!-- 移动端底部快捷导航 -->
        <nav class="mobile-nav">
          <RouterLink
            v-for="item in navItems"
            :key="item.name"
            class="mobile-nav-item"
            :to="{ name: item.name }"
          >
            <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
            <span class="mobile-nav-label">{{ item.label }}</span>
            <span v-if="item.name === 'notifications' && unreadCount > 0" class="badge dot" />
          </RouterLink>
        </nav>
      </header>

      <main class="main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
}

/* ---- 侧边栏 ---- */
.sidebar {
  width: 224px;
  flex-shrink: 0;
  background: var(--color-surface-low);
  border-right: 1px solid var(--color-border);
  padding: var(--space-xl) var(--space-lg);
  display: none;
  flex-direction: column;
  gap: var(--space-xl);
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 700;
  color: var(--color-primary);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: 10px 12px;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 14px;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-item:hover {
  background: rgba(255, 182, 137, 0.08);
  color: var(--color-text);
}

.nav-item.router-link-active {
  background: rgba(242, 140, 69, 0.16);
  color: var(--color-primary);
  font-weight: 600;
}

.nav-icon {
  font-size: 16px;
}

.badge {
  margin-left: auto;
  background: var(--color-danger);
  color: #fff;
  font-size: 11px;
  line-height: 16px;
  padding: 0 6px;
  border-radius: var(--radius-full);
}

.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.user-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.avatar {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: var(--color-primary-strong);
  color: var(--color-on-primary);
  font-weight: 700;
  flex-shrink: 0;
}

.nickname {
  flex: 1;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---- 内容区 ---- */
.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  flex-direction: column;
  background: var(--color-surface-low);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 20;
}

.topbar-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
}

.brand-sm {
  font-family: var(--font-heading);
  font-weight: 700;
  color: var(--color-primary);
  flex: 1;
}

.baby-select-sm {
  max-width: 130px;
}

.mobile-nav {
  display: flex;
  border-top: 1px solid var(--color-border);
}

.mobile-nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 0 6px;
  font-size: 11px;
  color: var(--color-text-secondary);
  text-decoration: none;
  position: relative;
}

.mobile-nav-item.router-link-active {
  color: var(--color-primary);
}

.badge.dot {
  position: absolute;
  top: 6px;
  right: 22%;
  width: 8px;
  height: 8px;
  padding: 0;
  background: var(--color-danger);
  border-radius: var(--radius-full);
}

.main {
  flex: 1;
}

/* ---- ≥768px：桌面侧边栏布局 ---- */
@media (min-width: 768px) {
  .sidebar {
    display: flex;
  }

  .topbar {
    display: none;
  }
}
</style>
