"""仅由管理员离线导入的、已审核公共教育资料；不接收宝宝记录。"""

from datetime import date
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.schemas.advisor import AdvisorSchema, advisor_today


class KnowledgeDocument(AdvisorSchema):
    document_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    source_url: HttpUrl
    version: str = Field(min_length=1, max_length=80)
    review_status: Literal["approved"]
    reviewed_by: str = Field(min_length=1, max_length=100)
    reviewed_on: date
    valid_until: date
    scope: Literal["general_education"]
    topics: list[Literal["growth_review", "diet_review", "recipe_recommendation", "feeding_knowledge"]] = Field(min_length=1, max_length=4)
    age_min_months: int = Field(0, ge=0, le=36)
    age_max_months: int = Field(36, ge=0, le=36)

    @model_validator(mode="after")
    def validate_review(self):
        if self.reviewed_on > advisor_today() or self.valid_until < self.reviewed_on:
            raise ValueError("审核日期或有效期无效")
        if self.age_max_months < self.age_min_months:
            raise ValueError("月龄范围无效")
        if not self.title.strip() or not self.version.strip() or not self.reviewed_by.strip():
            raise ValueError("文献和审核元数据不能为空")
        # 保留完整段落，避免截断上下文或丢失限定条件。
        if any(len(part.strip()) > 1200 for part in self.content.split("\n\n")):
            raise ValueError("每个知识段落最多1200字，请经审核后按完整语义分段")
        if not self.content.strip():
            raise ValueError("正文不能为空")
        return self
