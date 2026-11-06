import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AdvisorResult from '@/components/AdvisorResult.vue'
import { answerFixture } from './advisorFixture'

describe('顾问结果与引用', () => {
  it('引用能展开并聚焦对应来源；知识原文以纯文本展示', async () => {
    const answer = answerFixture({ generation_mode: 'agent_rag', agent_status: 'completed' })
    answer.sources.push({ id: 'knowledge:1', type: 'knowledge', label: '审核资料', as_of: null,
      url: 'https://example.org/reviewed', version: 'v1', reviewed_on: '2026-10-01' })
    answer.knowledge = [{ text: '<img src=x onerror=alert(1)>\n原始摘录', evidence_id: 'knowledge:1' }]
    const page = mount(AdvisorResult, { attachTo: document.body, props: { answer, question: '成长回顾', babyName: '演示宝宝' } })
    expect(page.find('.source-list').exists()).toBe(false)
    expect(page.find('blockquote img').exists()).toBe(false)
    expect(page.get('blockquote').text()).toContain('<img src=x onerror=alert(1)>')
    await page.get('blockquote .citations a').trigger('click')
    await flushPromises()
    expect(page.get('details').attributes('open')).toBeDefined()
    expect(document.activeElement?.textContent).toContain('审核资料')
    const link = page.get('.source-list a')
    expect(link.attributes('href')).toBe('https://example.org/reviewed')
    expect(link.attributes('rel')).toBe('noopener noreferrer')
    expect(page.get('.source-list').text()).toContain('审核日期 2026-10-01')
    page.unmount()
  })

  it('拒绝脚本、数据和带凭据的来源链接', async () => {
    const answer = answerFixture()
    answer.sources = ['javascript:alert(1)', 'data:text/html,<h1>x</h1>', 'https://name:password@example.org', '/relative'].map((url, index) => ({
      id: `source:${index}`, type: 'knowledge', label: `来源${index}`, as_of: null, url, version: null, reviewed_on: null
    }))
    const page = mount(AdvisorResult, { props: { answer, question: '回顾', babyName: '演示宝宝' } })
    const details = page.get('details')
    ;(details.element as HTMLDetailsElement).open = true
    await details.trigger('toggle')
    expect(page.findAll('.source-list li')).toHaveLength(4)
    expect(page.findAll('.source-list a')).toHaveLength(0)
    page.unmount()
  })

  it('模型失败显示回退说明，紧急求助优先显示且可拨打120', () => {
    const page = mount(AdvisorResult, { props: {
      answer: answerFixture({ agent_status: 'failed', safety_level: 'emergency', summary: '请立即拨打120。', observations: [] }),
      question: '宝宝呼吸困难', babyName: '演示宝宝'
    } })
    expect(page.text()).toContain('智能整理暂不可用')
    expect(page.get('.answer-summary[role="alert"]').text()).toContain('请立即寻求急救帮助')
    expect(page.get('.emergency-call').attributes('href')).toBe('tel:120')
    page.unmount()
  })
})
