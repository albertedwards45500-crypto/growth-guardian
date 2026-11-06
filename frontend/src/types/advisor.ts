/** 与后端只读顾问契约对应，不包含用户身份、模型密钥或写操作。 */
export type AdvisorIntent = 'growth_review' | 'diet_review' | 'recipe_recommendation' | 'feeding_knowledge'

export interface AdvisorRequest {
  question: string
  intent?: AdvisorIntent
  as_of?: string
  days?: number
}

export interface AdvisorCapabilities {
  agent: 'disabled' | 'unconfigured' | 'configured'
  knowledge: 'disabled' | 'unconfigured' | 'configured'
  today: string
}

export interface AdvisorSource {
  id: string
  type: string
  label: string
  as_of: string | null
  url: string | null
  version: string | null
  reviewed_on: string | null
}

export interface AdvisorStatement {
  text: string
  evidence_ids: string[]
}

export interface AdvisorAnswer {
  schema_version: '1.0'
  request_id: string
  generation_mode: 'rules' | 'agent' | 'agent_rag'
  agent_status: 'disabled' | 'completed' | 'unavailable' | 'failed' | 'skipped_safety'
  as_of: string
  intent: AdvisorIntent | 'clarification_needed'
  safety_level: 'normal' | 'caution' | 'urgent' | 'emergency'
  summary: string
  observations: AdvisorStatement[]
  recommendations: Array<AdvisorStatement & { type: 'monitoring' | 'recipe_candidate' | 'seek_care'; priority: 'normal' | 'high' }>
  risks: string[]
  missing_information: string[]
  sources: AdvisorSource[]
  recipe_candidates: Array<{ recipe_id: number; title: string; ingredients: string[]; nutrition_tags: string[]; evidence_ids: string[] }>
  knowledge: Array<{ text: string; evidence_id: string }>
  tool_statuses: Array<{ tool: string; status: 'ok' | 'partial' | 'no_data' | 'invalid'; warnings: string[]; missing: string[] }>
  actions: never[]
  disclaimer: string
}
