/**
 * @file: tests/babyStore.spec.ts
 * @description: 宝宝 store 缓存测试：ensureLoaded 复用缓存、force/invalidate 后重新拉取、登出失效缓存。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock 宝宝列表接口（store 唯一数据来源）
vi.mock('@/api/babies', () => ({
  listBabies: vi.fn()
}))

import { listBabies } from '@/api/babies'
import { useAuthStore } from '@/stores/auth'
import { useBabyStore } from '@/stores/baby'
import type { Baby } from '@/types/api'

/** 测试用宝宝档案 */
const mockBaby: Baby = {
  id: 1,
  name: '豆豆',
  gender: null,
  birth_date: '2026-01-01',
  avatar_url: null,
  is_default: true,
  created_at: '2026-01-01T00:00:00'
}

/**
 * 将 listBabies mock 断言为返回单个测试档案。
 */
function mockListResolved(): void {
  ;(listBabies as ReturnType<typeof vi.fn>).mockResolvedValue([mockBaby])
}

describe('baby store 缓存', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('ensureLoaded 首次拉取列表，重复调用复用缓存', async () => {
    mockListResolved()
    const store = useBabyStore()

    await store.ensureLoaded()
    await store.ensureLoaded()

    expect(listBabies).toHaveBeenCalledTimes(1)
    expect(store.loaded).toBe(true)
    expect(store.babies).toHaveLength(1)
  })

  it('force=true 时忽略缓存强制重新拉取', async () => {
    mockListResolved()
    const store = useBabyStore()

    await store.ensureLoaded()
    await store.ensureLoaded(true)

    expect(listBabies).toHaveBeenCalledTimes(2)
  })

  it('invalidate 失效缓存后 ensureLoaded 重新拉取', async () => {
    mockListResolved()
    const store = useBabyStore()

    await store.ensureLoaded()
    store.invalidate()
    expect(store.loaded).toBe(false)

    await store.ensureLoaded()
    expect(listBabies).toHaveBeenCalledTimes(2)
  })

  it('拉取失败不置 loaded 标记，下次仍会重试', async () => {
    ;(listBabies as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('网络错误'))
    const store = useBabyStore()

    await expect(store.ensureLoaded()).rejects.toThrow('网络错误')
    expect(store.loaded).toBe(false)

    mockListResolved()
    await store.ensureLoaded()
    expect(listBabies).toHaveBeenCalledTimes(2)
  })

  it('登出时失效宝宝列表缓存', async () => {
    mockListResolved()
    const store = useBabyStore()
    await store.ensureLoaded()
    expect(store.loaded).toBe(true)

    useAuthStore().logout()

    expect(store.loaded).toBe(false)
  })
})
