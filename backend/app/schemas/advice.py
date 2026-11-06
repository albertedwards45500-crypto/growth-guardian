"""
@file: app/schemas/advice.py
@description: 专业建议模块相关 Pydantic Schema：指南与 FAQ。
"""

from pydantic import BaseModel, Field


class GuideResponse(BaseModel):
    """分月龄喂养指南响应模型。"""

    id: int
    month_start: int
    month_end: int
    title: str
    content: str
    food_suggestions: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FaqResponse(BaseModel):
    """常见问题响应模型。"""

    id: int
    category: str
    question: str
    answer: str

    model_config = {"from_attributes": True}
