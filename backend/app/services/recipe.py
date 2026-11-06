"""
@file: app/services/recipe.py
@description: 辅食推荐业务服务：食谱筛选与过敏规避推荐引擎。
"""

from sqlalchemy import String, and_, cast, func
from sqlalchemy.orm import Session

from app.models.baby import Baby
from app.models.diet import Allergy
from app.models.recipe import Recipe


def recommend_recipes(
    db: Session,
    baby: Baby,
    age_months: int | None = None,
    ingredient: str | None = None,
    nutrition: str | None = None,
    keyword: str | None = None,
    exclude_allergens: bool = True,
    limit: int | None = None,
) -> list[Recipe]:
    """推荐/筛选食谱（条件全部下推 SQL，避免全表加载后内存过滤）。

    筛选条件（均可选）：
    - 月龄：食谱适合区间需覆盖宝宝月龄；
    - 食材：食谱食材清单包含指定食材关键词；
    - 营养：食谱营养标签匹配；
    - 关键词：食谱名称模糊匹配；
    - 过敏规避：SQL WHERE 下推自动排除包含宝宝过敏食材的食谱（立项书 4.2/4.3）。

    过敏过滤实现说明（JSON 列 LIKE 方案）：
    - ingredients 为 JSON 列，MySQL 的 JSON_CONTAINS / SQLite 的 json_each
      均不可跨库移植，故采用 NOT LIKE 文本排除；
    - 匹配模式 `%"%食材名%"` ：命中食材名作为 JSON 字符串值（或值内子串）
      出现的位置，语义与原 Python 端"子串包含"判断一致；
    - 前提：写入统一使用无空格紧凑 JSON 且中文不转义（见
      app/core/database.py::_json_serializer），食材名两侧紧贴双引号，
      种子数据与用户输入走同一序列化器，形态一致；
    - 兼容性：SQLite 的 lower() 仅处理 ASCII、LIKE 对 ASCII 默认不区分
      大小写；中文无大小写差异；MySQL 侧 JSON 列参与字符串函数时自动
      文本化（其默认文本格式带空格，但本模式仅依赖名称两侧引号，不受
      空格影响），且 utf8mb4 通用排序规则同样不区分大小写。

    @param db: 数据库会话
    @param baby: 宝宝档案（用于过敏规避与月龄计算）
    @param age_months: 目标月龄，缺省按宝宝出生日期计算
    @param ingredient: 食材关键词
    @param nutrition: 营养标签关键词
    @param keyword: 名称关键词
    @param exclude_allergens: 是否排除含过敏食材的食谱
    @param limit: 可选查询上限（1-201），顾问工具使用；默认保持原有全量行为
    @return: 匹配的食谱列表（按 id 升序，排序逻辑与原实现保持一致）
    @raises ValueError: 月龄无法解析时由 compute_age 抛出
    """
    from app.services.growth import compute_age

    age = age_months if age_months is not None else compute_age(baby.birth_date)[0]

    # D10 下推：上架状态与月龄适配直接作为 SQL WHERE 条件
    query = db.query(Recipe).filter(
        Recipe.is_active.is_(True),
        Recipe.suitable_age_min <= age,
        Recipe.suitable_age_max >= age,
    )

    # 食材关键词：对 JSON 字段文本进行模糊匹配
    if ingredient:
        query = query.filter(cast(Recipe.ingredients, String).like(f"%{ingredient}%"))
    # 营养标签
    if nutrition:
        query = query.filter(cast(Recipe.nutrition_tags, String).like(f"%{nutrition}%"))
    # 名称模糊搜索
    if keyword:
        query = query.filter(Recipe.title.like(f"%{keyword}%"))

    # D10 下推：过敏规避由 Python 内存过滤改为 SQL NOT LIKE 条件
    if exclude_allergens and baby is not None:
        allergens = [
            row[0].strip().lower()
            for row in db.query(Allergy.ingredient)
            .filter(Allergy.baby_id == baby.id)
            .all()
            if row[0] and row[0].strip()
        ]
        if allergens:
            # 逐个过敏食材追加 NOT LIKE 排除条件（列 lower 后与过敏名小写比较，
            # 对齐原实现的 lower() 子串语义；模式中的 % 为 LIKE 通配符，
            # 由 SQLAlchemy 参数绑定传递，无注入风险）
            query = query.filter(
                and_(
                    *[
                        func.lower(Recipe.ingredients).notlike(f'%"{a}%"%')
                        for a in allergens
                    ]
                )
            )

    query = query.order_by(Recipe.id.asc())
    if limit is not None:
        if not 1 <= limit <= 201:
            raise ValueError("食谱查询上限必须在1至201之间")
        query = query.limit(limit)
    return query.all()


def get_recipe_or_404(db: Session, recipe_id: int) -> Recipe:
    """按 ID 获取上架食谱。

    @param db: 数据库会话
    @param recipe_id: 食谱 ID
    @return: 食谱实例
    @raises NotFoundError: 不存在或未上架时抛出
    """
    from app.core.exceptions import NotFoundError

    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.is_active.is_(True)).first()
    if recipe is None:
        raise NotFoundError("食谱不存在或已下架")
    return recipe
