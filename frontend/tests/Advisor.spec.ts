import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Advisor from '@/views/Advisor.vue'
import { useBabyStore } from '@/stores/baby'
import { askAdvisor, getAdvisorStatus } from '@/api/advisor'
import type { AdvisorAnswer, AdvisorCapabilities } from '@/types/advisor'
import { answerFixture, babyFixture } from './advisorFixture'

vi.mock('@/api/advisor', () => ({ askAdvisor: vi.fn(), getAdvisorStatus: vi.fn() }))
vi.mock('@/api/babies', () => ({ listBabies: vi.fn() }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('成长顾问页面', () => {
  let wrapper: VueWrapper | undefined
  let pinia: Pinia
  const capabilities: AdvisorCapabilities = { agent: 'configured', knowledge: 'disabled', today: '2026-10-23' }

  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    pinia = createPinia()
    setActivePinia(pinia)
    const store = useBabyStore()
    store.babies = [babyFixture, { ...babyFixture, id: 2, name: '演示安安', is_default: false }]
    store.currentBabyId = 1
    store.loaded = true
    vi.mocked(getAdvisorStatus).mockResolvedValue(capabilities)
    vi.mocked(askAdvisor).mockResolvedValue(answerFixture())
  })

  afterEach(() => { wrapper?.unmount(); wrapper = undefined })

  async function open() {
    wrapper = mount(Advisor, { attachTo: document.body, global: {
      plugins: [pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } }
    } })
    await flushPromises()
    return wrapper
  }

  it('没有有效档案时不请求顾问接口', async () => {
    useBabyStore().babies = []
    useBabyStore().currentBabyId = 999
    const page = await open()
    expect(page.text()).toContain('先创建宝宝档案')
    expect(getAdvisorStatus).not.toHaveBeenCalled()
    expect(askAdvisor).not.toHaveBeenCalled()
  })

  it('示例问题只填入表单，提交后显示结构化结果，且不持久化问答', async () => {
    const page = await open()
    expect(page.text()).toContain('智能整理已配置 · 知识资料暂未启用')
    await page.findAll('.preset-button')[0].trigger('click')
    expect(askAdvisor).not.toHaveBeenCalled()
    expect((page.get('#advisor-question').element as HTMLTextAreaElement).value).toContain('身高和体重')
    await page.get('form').trigger('submit')
    await flushPromises()
    expect(askAdvisor).toHaveBeenCalledWith(1, {
      question: '回顾最近的身高和体重记录，有哪些数值变化？', intent: 'growth_review'
    }, expect.any(AbortSignal))
    expect(page.text()).toContain('演示豆豆的记录回顾')
    expect(page.text()).toContain('最近录入的体重为8.5千克')
    expect(page.text()).toContain('还需要核实的信息')
    expect(document.activeElement).toBe(page.get('.answer-area').element)
    expect(localStorage.length).toBe(0)
  })

  it('拒绝空问题、越界日期和小数天数', async () => {
    const page = await open()
    await page.get('form').trigger('submit')
    expect(page.text()).toContain('请输入2至500字')
    await page.get('#advisor-question').setValue('饮食回顾')
    await page.get('#advisor-date').setValue('2026-10-24')
    await page.get('form').trigger('submit')
    expect(page.text()).toContain('回顾日期应在宝宝出生日期与今天之间')
    await page.get('#advisor-date').setValue('2025-12-31')
    await page.get('form').trigger('submit')
    expect(page.text()).toContain('回顾日期应在宝宝出生日期与今天之间')
    await page.get('#advisor-date').setValue('2026-10-20')
    await page.get('#advisor-days').setValue('1.5')
    await page.get('form').trigger('submit')
    expect(page.text()).toContain('饮食回顾天数应为1至31的整数')
    expect(askAdvisor).not.toHaveBeenCalled()
  })

  it('请求失败保留问题，且不会自动重试', async () => {
    vi.mocked(askAdvisor).mockRejectedValue(new Error('网络暂不可用'))
    const page = await open()
    await page.get('#advisor-question').setValue('帮我回顾成长记录')
    await page.get('form').trigger('submit')
    await flushPromises()
    expect(page.text()).toContain('网络暂不可用')
    expect((page.get('#advisor-question').element as HTMLTextAreaElement).value).toBe('帮我回顾成长记录')
    expect(askAdvisor).toHaveBeenCalledTimes(1)
  })

  it('切走又切回同一宝宝，也拒绝旧请求和旧状态覆盖新上下文', async () => {
    const oldAsk = deferred<AdvisorAnswer>()
    const oldStatus = deferred<AdvisorCapabilities>()
    vi.mocked(askAdvisor).mockReturnValueOnce(oldAsk.promise)
    vi.mocked(getAdvisorStatus).mockReturnValueOnce(oldStatus.promise)
    const page = await open()
    const statusSignal = vi.mocked(getAdvisorStatus).mock.calls[0][1]!
    await page.get('#advisor-question').setValue('旧宝宝的成长问题')
    await page.get('form').trigger('submit')
    const askSignal = vi.mocked(askAdvisor).mock.calls[0][2]!
    const store = useBabyStore()
    store.setCurrentBaby(2)
    store.setCurrentBaby(1)
    await flushPromises()
    expect(askSignal.aborted).toBe(true)
    expect(statusSignal.aborted).toBe(true)
    await page.get('#advisor-question').setValue('切回后的新问题')
    await page.get('form').trigger('submit')
    await flushPromises()
    oldAsk.resolve(answerFixture({ summary: '禁止显示的过期回答' }))
    oldStatus.resolve({ ...capabilities, knowledge: 'configured' })
    await flushPromises()
    expect(page.text()).not.toContain('禁止显示的过期回答')
    expect(page.text()).toContain('切回后的新问题')
    expect(page.text()).toContain('知识资料暂未启用')
  })

  it('切换宝宝清除已显示的问答和草稿', async () => {
    const page = await open()
    await page.get('#advisor-question').setValue('演示豆豆成长回顾')
    await page.get('form').trigger('submit')
    await flushPromises()
    useBabyStore().setCurrentBaby(2)
    await flushPromises()
    expect(page.find('.advisor-result').exists()).toBe(false)
    expect(page.text()).not.toContain('演示豆豆成长回顾')
    expect((page.get('#advisor-question').element as HTMLTextAreaElement).value).toBe('')
  })

  it('重复提交只发一次；停止等待后迟到的响应不展示', async () => {
    const pending = deferred<AdvisorAnswer>()
    vi.mocked(askAdvisor).mockReturnValue(pending.promise)
    const page = await open()
    await page.get('#advisor-question').setValue('成长回顾')
    await page.get('form').trigger('submit')
    await page.get('form').trigger('submit')
    expect(askAdvisor).toHaveBeenCalledTimes(1)
    const signal = vi.mocked(askAdvisor).mock.calls[0][2]!
    await page.get('.cancel-button').trigger('click')
    expect(signal.aborted).toBe(true)
    expect(page.text()).toContain('刚才的请求可能仍在处理')
    pending.resolve(answerFixture())
    await flushPromises()
    expect(page.find('.advisor-result').exists()).toBe(false)
  })

  it('离开页面会取消状态读取和提问等待', async () => {
    vi.mocked(askAdvisor).mockReturnValue(new Promise(() => {}))
    vi.mocked(getAdvisorStatus).mockReturnValue(new Promise(() => {}))
    const page = await open()
    await page.get('#advisor-question').setValue('成长回顾')
    await page.get('form').trigger('submit')
    const askSignal = vi.mocked(askAdvisor).mock.calls[0][2]!
    const statusSignal = vi.mocked(getAdvisorStatus).mock.calls[0][1]!
    page.unmount()
    wrapper = undefined
    expect(askSignal.aborted).toBe(true)
    expect(statusSignal.aborted).toBe(true)
  })
})
