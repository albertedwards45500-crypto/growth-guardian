"""供人工核对的公共资料草稿；不能直接进入Qdrant。"""

from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.schemas.advisor import AdvisorSchema, advisor_today


class KnowledgeCandidate(AdvisorSchema):
    document_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    source_url: HttpUrl
    drafted_on: date
    source_checked_on: date | None = None
    source_excerpt: str | None = Field(None, min_length=1, max_length=500)
    source_section: str | None = Field(None, min_length=1, max_length=300)
    content_kind: Literal["source_summary", "translation_draft"] = "translation_draft"
    version: str = Field(min_length=1, max_length=80)
    review_status: Literal["pending"]
    reviewer_notes: str = Field(min_length=1, max_length=1000)
    scope: Literal["general_education"]
    topics: list[Literal["growth_review", "diet_review", "recipe_recommendation", "feeding_knowledge"]] = Field(min_length=1, max_length=4)
    age_min_months: int = Field(0, ge=0, le=36)
    age_max_months: int = Field(36, ge=0, le=36)

    @model_validator(mode="after")
    def validate_candidate(self):
        if self.drafted_on > advisor_today():
            raise ValueError("草稿日期不能晚于今天")
        if (self.source_checked_on is None) != (self.source_excerpt is None):
            raise ValueError("来源核对日期和原文摘录必须一起提供")
        if self.source_checked_on is not None and self.source_checked_on > advisor_today():
            raise ValueError("来源核对日期不能晚于今天")
        if self.source_excerpt is not None and not self.source_excerpt.strip():
            raise ValueError("原文摘录不能为空")
        if self.source_checked_on is not None and not (self.source_section or "").strip():
            raise ValueError("核对来源后须记录正文所在小节")
        if self.age_max_months < self.age_min_months:
            raise ValueError("月龄范围无效")
        if any(len(part.strip()) > 1200 for part in self.content.split("\n\n")):
            raise ValueError("每个知识段落最多1200字，请按完整语义分段")
        if not self.content.strip() or not self.reviewer_notes.strip():
            raise ValueError("草稿正文和审核说明不能为空")
        return self
