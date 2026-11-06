"""
@file: app/services/diet.py
@description: 饮食管理业务服务：营养分析聚合、过敏食材校验。
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.baby import Baby
from app.models.diet import DietRecord
from app.schemas.diet import NutritionSummary


def build_nutrition_summary(db: Session, baby: Baby, target_date: date) -> NutritionSummary:
    """按日期聚合宝宝饮食数据，生成营养分析摘要。

    母乳记录统计总时长（分钟）；配方奶记录统计总量（ml）；
    辅食记录统计次数与食材清单。

    @param db: 数据库会话
    @param baby: 宝宝档案
    @param target_date: 统计日期
    @return: NutritionSummary 摘要
    """
    records = (
        db.query(DietRecord)
        .filter(DietRecord.baby_id == baby.id, DietRecord.record_date == target_date)
        .all()
    )

    feed_count = len(records)
    breast_minutes = 0
    formula_ml = 0
    solid_count = 0
    food_names: set[str] = set()

    for rec in records:
        details = rec.details or {}
        if rec.record_type == "breast_milk":
            breast_minutes += int(details.get("left_minutes", 0) or 0)
            breast_minutes += int(details.get("right_minutes", 0) or 0)
        elif rec.record_type == "formula":
            formula_ml += int(details.get("amount_ml", 0) or 0)
        elif rec.record_type == "solid_food":
            solid_count += 1
            for item in details.get("food_items", []) or []:
                if isinstance(item, str):
                    food_names.add(item)

    return NutritionSummary(
        baby_id=baby.id,
        date=target_date,
        feed_count=feed_count,
        breast_milk_minutes=breast_minutes,
        formula_amount_ml=formula_ml,
        solid_food_count=solid_count,
        food_names=sorted(food_names),
    )
