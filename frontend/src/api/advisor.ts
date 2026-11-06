import { http } from './client'
import type { AdvisorAnswer, AdvisorCapabilities, AdvisorRequest } from '@/types/advisor'

export function getAdvisorStatus(babyId: number, signal?: AbortSignal): Promise<AdvisorCapabilities> {
  return http.get(`/babies/${babyId}/advisor/status`, { signal }) as unknown as Promise<AdvisorCapabilities>
}

export function askAdvisor(babyId: number, payload: AdvisorRequest, signal?: AbortSignal): Promise<AdvisorAnswer> {
  // 后端最多5轮，每轮60秒，另有Embedding/检索时间；单独覆盖普通接口的15秒超时。
  return http.post(`/babies/${babyId}/advisor/ask`, payload, { signal, timeout: 390000 }) as unknown as Promise<AdvisorAnswer>
}
