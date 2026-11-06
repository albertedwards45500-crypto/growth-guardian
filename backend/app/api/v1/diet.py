"""
@file: app/api/v1/diet.py
@description: 饮食管理接口：饮食记录 CRUD、营养分析、过敏食材管理。
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_baby_or_404, get_current_user
from app.core.exceptions import BusinessError, ConflictError, NotFoundError
from app.models.baby import Baby
from app.models.diet import Allergy, DietRecord
from app.models.user import User
from app.schemas.common import PageResult
from app.schemas.diet import (
    AllergyCreateRequest,
    AllergyResponse,
    DietRecordCreateRequest,
    DietRecordResponse,
    DietRecordUpdateRequest,
    NutritionSummary,
)
from app.services.diet import build_nutrition_summary

router = APIRouter(tags=["饮食管理"])


@router.post(
    "/babies/{baby_id}/diet-records",
    response_model=DietRecordResponse,
    summary="新增饮食记录",
)
def create_diet_record(
    baby_id: int,
    payload: DietRecordCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DietRecord:
    """新增饮食记录（母乳/配方奶/辅食三种类型）。

    @param baby_id: 宝宝档案 ID
    @param payload: 饮食记录数据
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 新建的饮食记录
    @raises BusinessError: 明细与记录类型不匹配时抛出
    """
    get_baby_or_404(baby_id, db, current_user.id)
    _validate_diet_details(payload.record_type, payload.details)

    record = DietRecord(
        baby_id=baby_id,
        record_date=payload.record_date,
        record_type=payload.record_type,
        details=payload.details,
        note=payload.note,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get(
    "/babies/{baby_id}/diet-records",
    response_model=PageResult[DietRecordResponse],
    summary="获取饮食记录列表",
)
def list_diet_records(
    baby_id: int,
    record_date: date | None = Query(None, description="按日期过滤（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PageResult:
    """查询宝宝的饮食记录，支持按日期过滤与标准分页（D09）。

    分页模式与食谱主列表对齐：page/page_size 由 Query 约束（ge=1、
    page_size<=100），非法参数由全局校验处理器统一转 42200；
    响应结构由裸列表变更为 {items, total, page, page_size}（复用 PageResult）。

    @param baby_id: 宝宝档案 ID
    @param record_date: 可选日期过滤
    @param page: 页码（从 1 开始）
    @param page_size: 每页条数（1-100）
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 分页结果（items 按记录时间倒序，id 倒序作为同秒稳定次序键）
    @raises NotFoundError: 宝宝档案不存在或不属于当前用户时抛出
    """
    get_baby_or_404(baby_id, db, current_user.id)
    query = db.query(DietRecord).filter(DietRecord.baby_id == baby_id)
    if record_date:
        query = query.filter(DietRecord.record_date == record_date)
    total = query.count()
    items = (
        # created_at 精度为秒，追加 id 倒序作为稳定次序键，保证分页不重不漏
        query.order_by(DietRecord.created_at.desc(), DietRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResult(items=items, total=total, page=page, page_size=page_size)


@router.put("/diet-records/{record_id}", response_model=DietRecordResponse, summary="更新饮食记录")
def update_diet_record(
    record_id: int,
    payload: DietRecordUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DietRecord:
    """更新饮食记录（字段均可选）。

    @param record_id: 记录 ID
    @param payload: 更新字段
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 更新后的饮食记录
    @raises NotFoundError: 记录不存在或不属于当前用户时抛出
    """
    record = db.query(DietRecord).filter(DietRecord.id == record_id).first()
    if record is None:
        raise NotFoundError("饮食记录不存在")
    get_baby_or_404(record.baby_id, db, current_user.id)

    new_type = payload.record_type or record.record_type
    new_details = payload.details if payload.details is not None else record.details
    _validate_diet_details(new_type, new_details)

    if payload.record_date is not None:
        record.record_date = payload.record_date
    if payload.record_type is not None:
        record.record_type = payload.record_type
    if payload.details is not None:
        record.details = payload.details
    if payload.note is not None:
        record.note = payload.note
    db.commit()
    db.refresh(record)
    return record


@router.delete("/diet-records/{record_id}", summary="删除饮食记录")
def delete_diet_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """删除饮食记录（校验归属）。

    @param record_id: 记录 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 删除结果提示
    @raises NotFoundError: 记录不存在时抛出
    """
    record = db.query(DietRecord).filter(DietRecord.id == record_id).first()
    if record is None:
        raise NotFoundError("饮食记录不存在")
    get_baby_or_404(record.baby_id, db, current_user.id)
    db.delete(record)
    db.commit()
    return {"deleted": True}


@router.get(
    "/babies/{baby_id}/diet-analysis",
    response_model=NutritionSummary,
    summary="获取营养分析",
)
def get_diet_analysis(
    baby_id: int,
    target_date: date = Query(..., description="分析日期（YYYY-MM-DD）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NutritionSummary:
    """按日期聚合宝宝饮食数据生成营养分析摘要。

    @param baby_id: 宝宝档案 ID
    @param target_date: 分析日期
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 营养分析摘要
    """
    baby = get_baby_or_404(baby_id, db, current_user.id)
    return build_nutrition_summary(db, baby, target_date)


@router.get(
    "/babies/{baby_id}/allergies",
    response_model=list[AllergyResponse],
    summary="获取过敏食材列表",
)
def list_allergies(
    baby_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Allergy]:
    """查询宝宝的过敏/偏好食材（推荐食谱时自动规避）。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 过敏食材列表
    """
    get_baby_or_404(baby_id, db, current_user.id)
    return db.query(Allergy).filter(Allergy.baby_id == baby_id).order_by(Allergy.id.asc()).all()


@router.post(
    "/babies/{baby_id}/allergies",
    response_model=AllergyResponse,
    summary="新增过敏食材",
)
def create_allergy(
    baby_id: int,
    payload: AllergyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Allergy:
    """记录宝宝过敏食材。

    @param baby_id: 宝宝档案 ID
    @param payload: 过敏食材数据
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 新建的过敏记录
    @raises ConflictError: 相同食材已记录时抛出
    """
    get_baby_or_404(baby_id, db, current_user.id)
    exists = (
        db.query(Allergy)
        .filter(Allergy.baby_id == baby_id, Allergy.ingredient == payload.ingredient)
        .first()
    )
    if exists:
        raise ConflictError("该食材已在过敏清单中")
    allergy = Allergy(
        baby_id=baby_id,
        ingredient=payload.ingredient,
        severity=payload.severity,
        note=payload.note,
    )
    db.add(allergy)
    db.commit()
    db.refresh(allergy)
    return allergy


@router.delete("/allergies/{allergy_id}", summary="删除过敏食材")
def delete_allergy(
    allergy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """删除过敏食材记录（校验归属）。

    @param allergy_id: 过敏记录 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 删除结果提示
    @raises NotFoundError: 记录不存在时抛出
    """
    allergy = db.query(Allergy).filter(Allergy.id == allergy_id).first()
    if allergy is None:
        raise NotFoundError("过敏记录不存在")
    get_baby_or_404(allergy.baby_id, db, current_user.id)
    db.delete(allergy)
    db.commit()
    return {"deleted": True}


def _validate_diet_details(record_type: str, details: dict | None) -> None:
    """校验饮食明细与记录类型匹配。

    @param record_type: 记录类型
    @param details: 明细字典
    @raises BusinessError: 明细缺失或字段不匹配时抛出
    """
    details = details or {}
    if record_type == "breast_milk":
        if "left_minutes" not in details and "right_minutes" not in details:
            raise BusinessError(40002, "母乳记录需填写喂养时长")
    elif record_type == "formula":
        if "amount_ml" not in details:
            raise BusinessError(40002, "配方奶记录需填写奶量(ml)")
    elif record_type == "solid_food":
        if "food_items" not in details:
            raise BusinessError(40002, "辅食记录需填写食材清单")
