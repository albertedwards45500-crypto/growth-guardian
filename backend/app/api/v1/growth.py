"""
@file: app/api/v1/growth.py
@description: 成长记录接口：生长记录 CRUD、生长曲线、里程碑管理。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_baby_or_404, get_current_user
from app.core.exceptions import NotFoundError
from app.models.baby import Baby
from app.models.growth import GrowthRecord, Milestone
from app.models.user import User
from app.schemas.growth import (
    GrowthCurveResponse,
    GrowthRecordCreateRequest,
    GrowthRecordResponse,
    MilestoneCreateRequest,
    MilestoneResponse,
)
from app.services.growth import build_growth_curve

router = APIRouter(tags=["成长记录"])


@router.post(
    "/babies/{baby_id}/growth-records",
    response_model=GrowthRecordResponse,
    summary="新增生长记录",
)
def create_growth_record(
    baby_id: int,
    payload: GrowthRecordCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GrowthRecord:
    """新增身高/体重/头围测量记录（至少填写一项测量指标）。

    @param baby_id: 宝宝档案 ID
    @param payload: 测量数据
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 新建的生长记录
    @raises BusinessError: 三项测量指标均未填写时抛出
    """
    get_baby_or_404(baby_id, db, current_user.id)
    if (
        payload.weight_kg is None
        and payload.height_cm is None
        and payload.head_circumference_cm is None
    ):
        from app.core.exceptions import BusinessError

        raise BusinessError(40001, "体重、身高、头围至少填写一项")

    record = GrowthRecord(
        baby_id=baby_id,
        record_date=payload.record_date,
        weight_kg=payload.weight_kg,
        height_cm=payload.height_cm,
        head_circumference_cm=payload.head_circumference_cm,
        note=payload.note,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get(
    "/babies/{baby_id}/growth-records",
    response_model=list[GrowthRecordResponse],
    summary="获取生长记录列表",
)
def list_growth_records(
    baby_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GrowthRecord]:
    """按时间倒序查询宝宝的生长记录。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 生长记录列表（按测量日期倒序）
    """
    get_baby_or_404(baby_id, db, current_user.id)
    return (
        db.query(GrowthRecord)
        .filter(GrowthRecord.baby_id == baby_id)
        .order_by(GrowthRecord.record_date.desc(), GrowthRecord.id.desc())
        .all()
    )


@router.get(
    "/babies/{baby_id}/growth-curve",
    response_model=GrowthCurveResponse,
    summary="获取生长曲线数据",
)
def get_growth_curve(
    baby_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GrowthCurveResponse:
    """获取生长曲线数据点（前端 ECharts 绘制，含月龄坐标）。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 按维度分组的曲线数据
    """
    baby = get_baby_or_404(baby_id, db, current_user.id)
    return build_growth_curve(db, baby)


@router.delete("/growth-records/{record_id}", summary="删除生长记录")
def delete_growth_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """删除生长记录（校验归属：记录需属于当前用户的宝宝）。

    @param record_id: 记录 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 删除结果提示
    @raises NotFoundError: 记录不存在或不属于当前用户时抛出
    """
    record = db.query(GrowthRecord).filter(GrowthRecord.id == record_id).first()
    if record is None:
        raise NotFoundError("生长记录不存在")
    # 归属校验：记录所属宝宝必须属于当前用户
    get_baby_or_404(record.baby_id, db, current_user.id)
    db.delete(record)
    db.commit()
    return {"deleted": True}


@router.get(
    "/babies/{baby_id}/milestones",
    response_model=list[MilestoneResponse],
    summary="获取里程碑列表",
)
def list_milestones(
    baby_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Milestone]:
    """查询宝宝的成长里程碑（按达成日期倒序）。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 里程碑列表
    """
    get_baby_or_404(baby_id, db, current_user.id)
    return (
        db.query(Milestone)
        .filter(Milestone.baby_id == baby_id)
        .order_by(Milestone.achieved_at.desc())
        .all()
    )


@router.post(
    "/babies/{baby_id}/milestones",
    response_model=MilestoneResponse,
    summary="新增里程碑",
)
def create_milestone(
    baby_id: int,
    payload: MilestoneCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Milestone:
    """记录宝宝达成某个发育里程碑（翻身/爬行/行走等）。

    @param baby_id: 宝宝档案 ID
    @param payload: 里程碑数据
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 新建的里程碑
    """
    get_baby_or_404(baby_id, db, current_user.id)
    milestone = Milestone(
        baby_id=baby_id,
        milestone_type=payload.milestone_type,
        name=payload.name,
        achieved_at=payload.achieved_at,
        note=payload.note,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.delete("/milestones/{milestone_id}", summary="删除里程碑")
def delete_milestone(
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """删除里程碑（校验归属）。

    @param milestone_id: 里程碑 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 删除结果提示
    @raises NotFoundError: 里程碑不存在时抛出
    """
    milestone = db.query(Milestone).filter(Milestone.id == milestone_id).first()
    if milestone is None:
        raise NotFoundError("里程碑不存在")
    get_baby_or_404(milestone.baby_id, db, current_user.id)
    db.delete(milestone)
    db.commit()
    return {"deleted": True}
