"""只读成长顾问的数据工具和回答契约。"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def advisor_today() -> date:
    """按产品所在时区确定日期，避免服务器时区影响快照范围。"""
    return datetime.now(timezone(timedelta(hours=8))).date()


class AdvisorSchema(BaseModel):
    """拒绝未声明字段，身份、过敏过滤和写操作不能由请求额外注入。"""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


AdvisorIntent = Literal["growth_review", "diet_review", "recipe_recommendation", "feeding_knowledge", "clarification_needed"]
SafetyLevel = Literal["normal", "caution", "urgent", "emergency"]
ToolStatus = Literal["ok", "partial", "no_data", "invalid"]


class AdvisorCapabilities(AdvisorSchema):
    """配置状态，不能据此保证模型在线或知识索引非空；不返回服务凭据。"""

    agent: Literal["disabled", "unconfigured", "configured"]
    knowledge: Literal["disabled", "unconfigured", "configured"]
    today: date


class AdvisorAskRequest(AdvisorSchema):
    question: str = Field(..., min_length=2, max_length=500)
    intent: Literal["growth_review", "diet_review", "recipe_recommendation", "feeding_knowledge"] | None = None
    as_of: date | None = None
    nutrition: str | None = Field(None, max_length=20)
    days: int = Field(7, ge=1, le=31, description="饮食回顾天数，含查询当天")

    @field_validator("question")
    @classmethod
    def non_blank_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("问题不能为空")
        return value

    @field_validator("as_of")
    @classmethod
    def no_future_snapshot(cls, value: date | None) -> date | None:
        if value is not None and value > advisor_today():
            raise ValueError("查询日期不能晚于今天")
        return value


class AdvisorSource(AdvisorSchema):
    id: str
    type: str
    label: str
    as_of: date | None = None
    url: str | None = None
    version: str | None = None
    reviewed_on: date | None = None


class AdvisorKnowledgeQuote(AdvisorSchema):
    text: str
    evidence_id: str


class AdvisorToolResult(AdvisorSchema):
    tool: str
    schema_version: Literal["1.0"] = "1.0"
    status: ToolStatus
    baby_id: int
    data: dict[str, Any] | None = None
    evidence: list[AdvisorSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class AdvisorStatement(AdvisorSchema):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class AdvisorRecommendation(AdvisorStatement):
    type: Literal["monitoring", "recipe_candidate", "seek_care"]
    priority: Literal["normal", "high"] = "normal"


class AdvisorRecipeCandidate(AdvisorSchema):
    recipe_id: int
    title: str
    ingredients: list[str]
    nutrition_tags: list[str]
    evidence_ids: list[str]


class AdvisorToolStatus(AdvisorSchema):
    tool: str
    status: ToolStatus
    warnings: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class AdvisorAnswer(AdvisorSchema):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    generation_mode: Literal["rules", "agent", "agent_rag"] = "rules"
    agent_status: Literal["disabled", "completed", "unavailable", "failed", "skipped_safety"] = "disabled"
    as_of: date
    intent: AdvisorIntent
    safety_level: SafetyLevel
    summary: str
    observations: list[AdvisorStatement] = Field(default_factory=list)
    recommendations: list[AdvisorRecommendation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    sources: list[AdvisorSource] = Field(default_factory=list)
    recipe_candidates: list[AdvisorRecipeCandidate] = Field(default_factory=list)
    knowledge: list[AdvisorKnowledgeQuote] = Field(default_factory=list)
    tool_statuses: list[AdvisorToolStatus] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=0)
    disclaimer: str = "仅用于整理成长与喂养记录，不能代替儿科医生的诊断或治疗。"

    @model_validator(mode="after")
    def evidence_must_exist(self) -> "AdvisorAnswer":
        source_ids = {source.id for source in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("来源编号不能重复")
        if any(not statement.evidence_ids for statement in self.observations):
            raise ValueError("事实观察必须提供数据来源")
        statements = [*self.observations, *self.recommendations]
        referenced = {evidence_id for statement in statements for evidence_id in statement.evidence_ids}
        referenced.update(
            evidence_id
            for recipe in self.recipe_candidates
            for evidence_id in recipe.evidence_ids
        )
        referenced.update(quote.evidence_id for quote in self.knowledge)
        if not referenced.issubset(source_ids):
            raise ValueError("回答引用了不存在的数据来源")
        return self
