"""
@file: app/schemas/recipe.py
@description: 食谱、收藏与辅食计划相关 Pydantic Schema。
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class RecipeQuery(BaseModel):
    """食谱筛选查询参数模型（对应立项书 4.3 多维筛选）。"""

    age_months: int | None = Field(None, ge=0, le=36, description="宝宝月龄")
    ingredient: str | None = Field(None, max_length=50, description="包含食材关键词")
    nutrition: str | None = Field(None, max_length=20, description="营养标签关键词")
    keyword: str | None = Field(None, max_length=50, description="名称模糊搜索")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")


class RecipeResponse(BaseModel):
    """食谱响应模型。"""

    id: int
    title: str
    cover_url: str | None = None
    suitable_age_min: int
    suitable_age_max: int
    ingredients: list[Any]
    steps: list[str]
    nutrition_tags: list[str]
    tips: str | None = None
    is_favorite: bool = Field(False, description="当前用户是否已收藏")
    created_at: datetime

    model_config = {"from_attributes": True}


class RecipeFavoriteResponse(BaseModel):
    """食谱收藏响应模型（含食谱概要）。"""

    id: int
    recipe_id: int
    recipe_title: str
    cover_url: str | None = None
    created_at: datetime


class MealPlanItemRequest(BaseModel):
    """单个辅食计划项请求模型。"""

    day_of_week: int = Field(..., ge=0, le=6, description="星期（0=周一）")
    meal_type: str = Field(..., description="餐次类型 breakfast/lunch/dinner/snack")
    recipe_id: int | None = Field(None, description="食谱ID，可空表示待定")
    note: str | None = Field(None, max_length=200, description="备注")


class MealPlanUpsertRequest(BaseModel):
    """整周辅食计划写入请求模型。"""

    week_start: date = Field(..., description="周起始日期（周一）")
    items: list[MealPlanItemRequest] = Field(default_factory=list, description="计划项列表")


class MealPlanItemResponse(BaseModel):
    """辅食计划项响应模型。"""

    id: int
    day_of_week: int
    meal_type: str
    recipe_id: int | None = None
    recipe_title: str | None = None
    note: str | None = None
