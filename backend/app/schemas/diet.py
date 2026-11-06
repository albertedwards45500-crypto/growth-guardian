"""
@file: app/schemas/diet.py
@description: 饮食记录与过敏食材相关 Pydantic Schema。
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# 饮食记录类型
DietType = Literal["breast_milk", "formula", "solid_food"]


class DietRecordCreateRequest(BaseModel):
    """新增饮食记录请求模型。

    @param record_date: 记录日期
    @param record_type: 记录类型
    @param details: 类型化明细，见各类型说明
    @param note: 备注
    """

    record_date: date = Field(..., description="记录日期")
    record_type: DietType = Field(..., description="记录类型")
    details: dict[str, Any] | None = Field(None, description="类型化明细")
    note: str | None = Field(None, max_length=500, description="备注")


class DietRecordUpdateRequest(BaseModel):
    """更新饮食记录请求模型（字段均可选）。"""

    record_date: date | None = None
    record_type: DietType | None = None
    details: dict[str, Any] | None = None
    note: str | None = None


class DietRecordResponse(BaseModel):
    """饮食记录响应模型。"""

    id: int
    baby_id: int
    record_date: date
    record_type: str
    details: dict[str, Any] | None = None
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AllergyCreateRequest(BaseModel):
    """新增过敏食材请求模型。"""

    ingredient: str = Field(..., min_length=1, max_length=50, description="食材名称")
    severity: str | None = Field(None, pattern="^(mild|moderate|severe)$", description="严重程度")
    note: str | None = Field(None, max_length=500, description="备注")


class AllergyResponse(BaseModel):
    """过敏食材响应模型。"""

    id: int
    baby_id: int
    ingredient: str
    severity: str | None = None
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NutritionSummary(BaseModel):
    """营养分析摘要模型（基于当日饮食记录）"""

    baby_id: int
    date: date
    feed_count: int = Field(0, description="喂养次数")
    breast_milk_minutes: int = Field(0, description="母乳总时长（分钟）")
    formula_amount_ml: int = Field(0, description="配方奶总量（ml）")
    solid_food_count: int = Field(0, description="辅食次数")
    food_names: list[str] = Field(default_factory=list, description="当日辅食食材清单")
