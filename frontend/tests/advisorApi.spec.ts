import { afterEach, describe, expect, it, vi } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import { askAdvisor, getAdvisorStatus } from '@/api/advisor'
import { http, TOKEN_KEY } from '@/api/client'
import { answerFixture } from './advisorFixture'

describe('顾问接口适配', () => {
  const originalAdapter = http.defaults.adapter
  afterEach(() => { http.defaults.adapter = originalAdapter; localStorage.clear() })

  it('复用身份和响应解包，仅顾问提问覆盖长超时并携带取消信号', async () => {
    localStorage.setItem(TOKEN_KEY, 'offline-test-token')
    const answer = answerFixture()
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => ({ data: { code: 0, message: 'ok', data: answer },
      status: 200, statusText: 'OK', headers: {}, config }))
    http.defaults.adapter = adapter
    const controller = new AbortController()
    const payload = { question: '成长回顾', intent: 'growth_review' as const }
    expect(await askAdvisor(2, payload, controller.signal)).toEqual(answer)
    const askConfig = adapter.mock.calls[0][0]
    expect(askConfig.url).toBe('/babies/2/advisor/ask')
    expect(askConfig.headers.Authorization).toBe('Bearer offline-test-token')
    expect(JSON.parse(askConfig.data)).toEqual(payload)
    expect(askConfig.signal).toBe(controller.signal)
    expect(askConfig.timeout).toBe(390000)
    await getAdvisorStatus(2, controller.signal)
    const statusConfig = adapter.mock.calls[1][0]
    expect(statusConfig.url).toBe('/babies/2/advisor/status')
    expect(statusConfig.timeout).toBe(15000)
    expect(statusConfig.signal).toBe(controller.signal)
  })
})
