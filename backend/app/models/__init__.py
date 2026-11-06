"""
@file: app/models/__init__.py
@description: 模型包导出，集中导入所有 ORM 模型，供 create_all / Alembic 元数据收集。
"""

from app.models.advice import Faq, Guide
from app.models.baby import Baby
from app.models.diet import Allergy, DietRecord
from app.models.growth import GrowthRecord, Milestone
from app.models.notification import Notification
from app.models.recipe import MealPlan, Recipe, RecipeFavorite
from app.models.user import User

__all__ = [
    "User",
    "Baby",
    "GrowthRecord",
    "Milestone",
    "DietRecord",
    "Allergy",
    "Recipe",
    "RecipeFavorite",
    "MealPlan",
    "Guide",
    "Faq",
    "Notification",
]
