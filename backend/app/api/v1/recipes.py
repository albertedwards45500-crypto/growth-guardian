"""
@file: app/api/v1/recipes.py
@description: 辅食推荐接口：食谱筛选、详情、收藏、智能推荐与一周辅食计划。
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_baby_or_404, get_current_user
from app.core.exceptions import BusinessError, NotFoundError
from app.models.baby import Baby
from app.models.recipe import MealPlan, Recipe, RecipeFavorite
from app.models.user import User
from app.schemas.common import PageResult
from app.schemas.recipe import (
    MealPlanItemResponse,
    MealPlanUpsertRequest,
    RecipeFavoriteResponse,
    RecipeResponse,
)
from app.services.recipe import get_recipe_or_404, recommend_recipes

router = APIRouter(tags=["辅食推荐"])


@router.get("/recipes", response_model=PageResult[RecipeResponse], summary="食谱列表与筛选")
def list_recipes(
    age_months: int | None = Query(None, ge=0, le=36, description="宝宝月龄"),
    ingredient: str | None = Query(None, description="食材关键词"),
    nutrition: str | None = Query(None, description="营养标签关键词"),
    keyword: str | None = Query(None, description="名称关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PageResult:
    """按月龄/食材/营养/关键词多维筛选食谱并分页（立项书 4.3）。

    @param age_months: 月龄筛选
    @param ingredient: 食材筛选
    @param nutrition: 营养标签筛选
    @param keyword: 名称搜索
    @param page: 页码
    @param page_size: 每页条数
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 分页食谱结果（含是否已收藏标记）
    """
    query = db.query(Recipe).filter(Recipe.is_active.is_(True))
    if age_months is not None:
        query = query.filter(
            Recipe.suitable_age_min <= age_months, Recipe.suitable_age_max >= age_months
        )
    if ingredient:
        query = query.filter(cast(Recipe.ingredients, String).like(f"%{ingredient}%"))
    if nutrition:
        query = query.filter(cast(Recipe.nutrition_tags, String).like(f"%{nutrition}%"))
    if keyword:
        query = query.filter(Recipe.title.like(f"%{keyword}%"))

    total = query.count()
    recipes = query.order_by(Recipe.id.asc()).offset((page - 1) * page_size).limit(page_size).all()

    favorite_ids = _favorite_recipe_ids(db, current_user.id)
    items = [_to_response(r, r.id in favorite_ids) for r in recipes]
    return PageResult(items=items, total=total, page=page, page_size=page_size)


@router.get("/recipes/favorites", response_model=list[RecipeFavoriteResponse], summary="我的收藏")
def list_favorites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RecipeFavoriteResponse]:
    """查询当前用户收藏的食谱列表。

    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 收藏列表（含食谱概要）
    """
    rows = (
        db.query(RecipeFavorite, Recipe)
        .join(Recipe, Recipe.id == RecipeFavorite.recipe_id)
        .filter(RecipeFavorite.user_id == current_user.id, Recipe.is_active.is_(True))
        .order_by(RecipeFavorite.created_at.desc())
        .all()
    )
    return [
        RecipeFavoriteResponse(
            id=fav.id,
            recipe_id=recipe.id,
            recipe_title=recipe.title,
            cover_url=recipe.cover_url,
            created_at=fav.created_at,
        )
        for fav, recipe in rows
    ]


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse, summary="食谱详情")
def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecipeResponse:
    """获取食谱详情（含制作步骤与食材清单）。

    @param recipe_id: 食谱 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 食谱详情
    """
    recipe = get_recipe_or_404(db, recipe_id)
    favorite_ids = _favorite_recipe_ids(db, current_user.id)
    return _to_response(recipe, recipe.id in favorite_ids)


@router.post("/recipes/{recipe_id}/favorite", summary="收藏食谱")
def favorite_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """收藏食谱（幂等：重复收藏直接返回成功）。

    收藏语义由数据库唯一约束 uq_recipe_favorites_user_recipe 兜底：
    先查重跳过重复插入；并发场景下若仍触发唯一冲突，则回滚后按幂等
    处理直接返回成功（D07）。

    @param recipe_id: 食谱 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 操作结果
    @raises NotFoundError: 食谱不存在或已下架时抛出
    @raises BusinessError: 非唯一约束类数据库异常向上透传为 50000
    """
    get_recipe_or_404(db, recipe_id)
    exists = (
        db.query(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.recipe_id == recipe_id,
        )
        .first()
    )
    if not exists:
        db.add(RecipeFavorite(user_id=current_user.id, recipe_id=recipe_id))
        try:
            db.commit()
        except IntegrityError:
            # 并发重复收藏命中唯一约束：回滚本次插入，按幂等语义返回成功
            db.rollback()
    return {"favorited": True}


@router.delete("/recipes/{recipe_id}/favorite", summary="取消收藏")
def unfavorite_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """取消收藏食谱（幂等）。

    @param recipe_id: 食谱 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 操作结果
    """
    db.query(RecipeFavorite).filter(
        RecipeFavorite.user_id == current_user.id,
        RecipeFavorite.recipe_id == recipe_id,
    ).delete()
    db.commit()
    return {"favorited": False}


@router.get(
    "/babies/{baby_id}/recipes/recommendations",
    response_model=PageResult[RecipeResponse],
    summary="智能推荐食谱",
)
def recommend_for_baby(
    baby_id: int,
    nutrition: str | None = Query(None, description="营养标签关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PageResult:
    """根据宝宝月龄与过敏史智能推荐食谱（自动规避过敏食材，D09 标准分页）。

    过敏与月龄过滤已由服务层下推 SQL（D10）；推荐结果集规模为食谱库级别，
    此处取全量匹配后按排序内存切片，保证 total 与排序口径一致。

    @param baby_id: 宝宝档案 ID
    @param nutrition: 可选营养标签筛选
    @param page: 页码（从 1 开始，非法值由全局校验处理器转 42200）
    @param page_size: 每页条数（1-100）
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 分页推荐结果（items + total + page + page_size）
    @raises NotFoundError: 宝宝档案不存在或不属于当前用户时抛出
    """
    baby = get_baby_or_404(baby_id, db, current_user.id)
    recipes = recommend_recipes(db, baby, nutrition=nutrition, exclude_allergens=True)
    favorite_ids = _favorite_recipe_ids(db, current_user.id)
    total = len(recipes)
    start = (page - 1) * page_size
    items = [
        _to_response(r, r.id in favorite_ids) for r in recipes[start : start + page_size]
    ]
    return PageResult(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/babies/{baby_id}/meal-plans",
    response_model=list[MealPlanItemResponse],
    summary="获取一周辅食计划",
)
def get_meal_plans(
    baby_id: int,
    week_start: date = Query(..., description="周起始日期（周一）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MealPlanItemResponse]:
    """查询宝宝某一周的辅食计划。

    @param baby_id: 宝宝档案 ID
    @param week_start: 周起始日期
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 计划项列表（含食谱名称）
    """
    get_baby_or_404(baby_id, db, current_user.id)
    rows = (
        db.query(MealPlan, Recipe)
        .outerjoin(Recipe, Recipe.id == MealPlan.recipe_id)
        .filter(MealPlan.baby_id == baby_id, MealPlan.week_start == week_start)
        .order_by(MealPlan.day_of_week.asc(), MealPlan.id.asc())
        .all()
    )
    return [
        MealPlanItemResponse(
            id=plan.id,
            day_of_week=plan.day_of_week,
            meal_type=plan.meal_type,
            recipe_id=plan.recipe_id,
            recipe_title=recipe.title if recipe else None,
            note=plan.note,
        )
        for plan, recipe in rows
    ]


@router.put(
    "/babies/{baby_id}/meal-plans",
    response_model=list[MealPlanItemResponse],
    summary="保存一周辅食计划",
)
def upsert_meal_plans(
    baby_id: int,
    payload: MealPlanUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MealPlanItemResponse]:
    """整体覆盖保存某一周的辅食计划（显式事务：先清空该周旧计划再写入，D07）。

    "查询现有记录 → 全部删除 → 插入新记录" 全程在同一 session 的同一
    事务内执行，仅在全部写入成功后统一 commit；任一步骤失败（如引用
    不存在的食谱触发外键冲突、计划槽位命中唯一约束 uq_meal_plans_slot）
    则整体 rollback，保证旧计划数据不被误删。

    @param baby_id: 宝宝档案 ID
    @param payload: 整周计划数据
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 保存后的计划项列表
    @raises NotFoundError: 宝宝档案不存在或不属于当前用户时抛出
    @raises BusinessError: 保存过程触发数据库完整性冲突时抛出 50000
    """
    get_baby_or_404(baby_id, db, current_user.id)
    try:
        # 显式事务（D07）：删除与插入同事务，异常整体回滚
        db.query(MealPlan).filter(
            MealPlan.baby_id == baby_id, MealPlan.week_start == payload.week_start
        ).delete(synchronize_session=False)

        for item in payload.items:
            db.add(
                MealPlan(
                    baby_id=baby_id,
                    week_start=payload.week_start,
                    day_of_week=item.day_of_week,
                    meal_type=item.meal_type,
                    recipe_id=item.recipe_id,
                    note=item.note,
                )
            )
        db.commit()
    except IntegrityError as exc:
        # 外键冲突（recipe_id 不存在）或槽位唯一冲突：回滚保留旧计划
        db.rollback()
        raise BusinessError(50000, "一周辅食计划保存失败：计划项冲突或引用的食谱不存在") from exc
    return get_meal_plans(baby_id, payload.week_start, db, current_user)


def _favorite_recipe_ids(db: Session, user_id: int) -> set[int]:
    """查询用户已收藏的食谱 ID 集合。

    @param db: 数据库会话
    @param user_id: 用户 ID
    @return: 已收藏食谱 ID 集合
    """
    rows = db.query(RecipeFavorite.recipe_id).filter(RecipeFavorite.user_id == user_id).all()
    return {r[0] for r in rows}


def _to_response(recipe: Recipe, is_favorite: bool) -> RecipeResponse:
    """将食谱 ORM 转换为响应模型并附带收藏标记。

    @param recipe: 食谱实例
    @param is_favorite: 是否已收藏
    @return: 食谱响应模型
    """
    return RecipeResponse(
        id=recipe.id,
        title=recipe.title,
        cover_url=recipe.cover_url,
        suitable_age_min=recipe.suitable_age_min,
        suitable_age_max=recipe.suitable_age_max,
        ingredients=recipe.ingredients or [],
        steps=recipe.steps or [],
        nutrition_tags=recipe.nutrition_tags or [],
        tips=recipe.tips,
        is_favorite=is_favorite,
        created_at=recipe.created_at,
    )
