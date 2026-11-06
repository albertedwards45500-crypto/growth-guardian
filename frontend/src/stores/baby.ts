/**
 * @file: src/stores/baby.ts
 * @description: 宝宝档案状态 store：档案列表与当前选中宝宝（全局默认上下文）。
 */

import { defineStore } from 'pinia'
import { listBabies } from '@/api/babies'
import type { Baby } from '@/types/api'

/** localStorage 中保存当前宝宝 ID 的键名 */
const CURRENT_BABY_KEY = 'czb_current_baby'

/** 宝宝 store 的状态结构 */
interface BabyState {
  /** 宝宝档案列表 */
  babies: Baby[]
  /** 当前选中的宝宝 ID */
  currentBabyId: number | null
  /** 列表加载中标记 */
  loading: boolean
  /** 列表已加载标记（用于同一次会话内的缓存去重） */
  loaded: boolean
}

/**
 * 从 localStorage 恢复上次选中的宝宝 ID。
 *
 * @returns 宝宝 ID 或 null
 */
function restoreCurrentBabyId(): number | null {
  const raw = localStorage.getItem(CURRENT_BABY_KEY)
  if (raw === null) return null
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * 宝宝档案 store：维护全局当前宝宝上下文，供各业务页共享。
 */
export const useBabyStore = defineStore('baby', {
  state: (): BabyState => ({
    babies: [],
    currentBabyId: restoreCurrentBabyId(),
    loading: false,
    loaded: false
  }),
  getters: {
    /**
     * 当前选中的宝宝对象。
     *
     * @param state: store 状态
     * @returns 当前宝宝，无档案时为 null
     */
    currentBaby: (state): Baby | null =>
      state.babies.find((b) => b.id === state.currentBabyId) ?? null,
    /**
     * 默认宝宝档案。
     *
     * @param state: store 状态
     * @returns 默认宝宝，无档案时为 null
     */
    defaultBaby: (state): Baby | null => state.babies.find((b) => b.is_default) ?? null
  },
  actions: {
    /**
     * 拉取宝宝列表并校准当前选中宝宝。
     *
     * 优先恢复上次选择，其次默认档案，再次首个档案。
     * 成功后置 loaded 标记，供 ensureLoaded 做缓存去重。
     *
     * @throws Error 未认证或网络错误时抛出（此时不置 loaded，便于下次重试）
     */
    async fetchBabies(): Promise<void> {
      this.loading = true
      try {
        this.babies = await listBabies()
        this.loaded = true
        if (this.babies.length === 0) {
          this.currentBabyId = null
          return
        }
        const stillExists = this.babies.some((b) => b.id === this.currentBabyId)
        if (!stillExists) {
          this.currentBabyId = (this.defaultBaby ?? this.babies[0]).id
        }
        localStorage.setItem(CURRENT_BABY_KEY, String(this.currentBabyId))
      } finally {
        this.loading = false
      }
    },
    /**
     * 确保列表已加载：已加载则直接复用缓存，否则拉取一次。
     *
     * 路由守卫、布局与各业务页统一经由本方法获取宝宝列表，
     * 避免同一次导航内 Layout 与页面组件各自重复请求。
     *
     * @param force: 为 true 时忽略缓存强制重新拉取（数据变更后使用）
     * @throws Error 未认证或网络错误时抛出
     */
    async ensureLoaded(force = false): Promise<void> {
      if (this.loaded && !force) return
      await this.fetchBabies()
    },
    /**
     * 失效列表缓存：登出或切换账号后调用，确保下次进入页面重新拉取。
     */
    invalidate(): void {
      this.loaded = false
    },
    /**
     * 切换当前宝宝并持久化选择。
     *
     * @param babyId: 目标宝宝 ID
     */
    setCurrentBaby(babyId: number): void {
      if (this.babies.some((b) => b.id === babyId)) {
        this.currentBabyId = babyId
        localStorage.setItem(CURRENT_BABY_KEY, String(babyId))
      }
    }
  }
})
