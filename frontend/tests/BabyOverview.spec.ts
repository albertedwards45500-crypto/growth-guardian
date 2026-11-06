/**
 * @file: tests/BabyOverview.spec.ts
 * @description: 宝宝概览页测试：里程碑以中文名渲染（无原始下划线键）、含「成长印记」标题、宝宝列表经 store 缓存去重。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { mount, type VueWrapper } from '@vue/test-utils'
import BabyOverview from '@/views/BabyOverview.vue'
import { useBabyStore } from '@/stores/baby'
import type { Baby, GrowthSummary } from '@/types/api'

// Mock 宝宝档案接口模块（页面挂载会拉取列表与成长印记）
vi.mock('@/api/babies', () => ({
  listBabies: vi.fn(),
  createBaby: vi.fn(),
  updateBaby: vi.fn(),
  deleteBaby: vi.fn(),
  getBabySummary: vi.fn()
}))

import { getBabySummary, listBabies } from '@/api/babies'

/** 测试用宝宝档案 */
const mockBaby: Baby = {
  id: 1,
  name: '豆豆',
  gender: 'female',
  birth_date: '2026-01-01',
  avatar_url: null,
  is_default: true,
  created_at: '2026-01-01T00:00:00'
}

/** 测试用成长印记数据：键为后端格式 `{milestone_type}_{中文名}` */
const mockSummary: GrowthSummary = {
  baby_id: 1,
  baby_name: '豆豆',
  age_months: 9,
  age_days: 5,
  stage_name: '爬行期',
  latest_weight_kg: 8.5,
  latest_height_cm: 72,
  latest_head_circumference_cm: 45,
  latest_measure_date: '2026-10-01',
  milestone_progress: {
    'roll_over_翻身': 1,
    'sit_独坐': 0,
    'crawl_爬行': 1,
    'stand_扶站': 0
  }
}

describe('BabyOverview.vue', () => {
  let pinia: Pinia

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    pinia = createPinia()
    setActivePinia(pinia)
    ;(listBabies as ReturnType<typeof vi.fn>).mockResolvedValue([mockBaby])
    ;(getBabySummary as ReturnType<typeof vi.fn>).mockResolvedValue(mockSummary)
  })

  /**
   * 挂载页面并等待异步加载完成。
   *
   * @returns 页面 wrapper
   */
  async function mountView(): Promise<VueWrapper> {
    const wrapper = mount(BabyOverview, { global: { plugins: [pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await vi.waitFor(() => {
      expect(wrapper.find('.milestone-progress').exists()).toBe(true)
    })
    return wrapper
  }

  it('渲染「成长印记」标题与里程碑中文标签，不含原始下划线键', async () => {
    const wrapper = await mountView()

    // 区块标题存在
    expect(wrapper.find('.imprint-title').text()).toBe('成长印记')

    // 里程碑标签按固定顺序渲染中文名 + 达成状态
    const tags = wrapper.findAll('.milestone-progress .tag').map((t) => t.text().trim())
    expect(tags).toEqual(['翻身 ✓', '独坐 ✗', '爬行 ✓', '扶站 ✗'])

    // 页面任何位置不出现原始类型键
    const text = wrapper.text()
    expect(text).not.toContain('roll_over')
    expect(text).not.toContain('sit_')
    expect(text).not.toContain('crawl_')
    expect(text).not.toContain('stand_')
  })

  it('同一次会话内重复挂载页面，宝宝列表仅请求一次（store 缓存去重）', async () => {
    const first = await mountView()
    first.unmount()

    // 再次进入页面（模拟路由切换）：复用 store 缓存，不重复请求
    const second = await mountView()
    second.unmount()

    expect(listBabies).toHaveBeenCalledTimes(1)
    // 成长印记按当前宝宝正常拉取
    expect(getBabySummary).toHaveBeenCalledWith(1)
  })

  it('数据变更后强制刷新列表重新拉取', async () => {
    await mountView()
    const store = useBabyStore()
    await store.fetchBabies()

    expect(listBabies).toHaveBeenCalledTimes(2)
    expect(store.loaded).toBe(true)
  })
})
