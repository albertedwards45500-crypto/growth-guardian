import type { Baby } from '@/types/api'
import type { AdvisorAnswer } from '@/types/advisor'

export const babyFixture: Baby = {
  id: 1, name: '演示豆豆', gender: 'female', birth_date: '2026-01-01',
  avatar_url: null, is_default: true, created_at: '2026-01-01T00:00:00'
}

export function answerFixture(overrides: Partial<AdvisorAnswer> = {}): AdvisorAnswer {
  return {
    schema_version: '1.0', request_id: 'test-request', generation_mode: 'rules', agent_status: 'disabled',
    as_of: '2026-10-23', intent: 'growth_review', safety_level: 'caution', summary: '已整理现有记录。',
    observations: [{ text: '最近录入的体重为8.5千克。', evidence_ids: ['growth:1'] }],
    recommendations: [], risks: ['记录无法用于判断疾病。'], missing_information: ['请补充最新测量。'],
    sources: [{ id: 'growth:1', type: 'growth_record', label: '体重记录', as_of: '2026-10-01', url: null, version: null, reviewed_on: null }],
    recipe_candidates: [], knowledge: [], tool_statuses: [], actions: [],
    disclaimer: '仅用于整理记录，不能替代诊疗。', ...overrides
  }
}
