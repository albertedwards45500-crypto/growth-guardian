"""
@file: app/api/v1/babies.py
@description: 宝宝档案接口：增删改查与成长印记聚合数据。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_baby_or_404, get_current_user
from app.core.exceptions import NotFoundError
from app.models.baby import Baby
from app.models.user import User
from app.schemas.baby import BabyCreateRequest, BabyResponse, BabyUpdateRequest
from app.schemas.growth import GrowthSummary
from app.services.growth import build_growth_summary

router = APIRouter(prefix="/babies", tags=["宝宝档案"])


@router.post("", response_model=BabyResponse, summary="创建宝宝档案")
def create_baby(
    payload: BabyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Baby:
    """为当前用户创建宝宝档案；首个档案自动设为默认。

    @param payload: 创建请求
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 新建的宝宝档案
    """
    baby = Baby(
        user_id=current_user.id,
        name=payload.name,
        gender=payload.gender,
        birth_date=payload.birth_date,
        avatar_url=payload.avatar_url,
    )
    has_baby = db.query(Baby).filter(Baby.user_id == current_user.id).first() is not None
    baby.is_default = not has_baby
    db.add(baby)
    db.commit()
    db.refresh(baby)
    return baby


@router.get("", response_model=list[BabyResponse], summary="获取宝宝档案列表")
def list_babies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Baby]:
    """查询当前用户的所有宝宝档案。

    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 宝宝档案列表
    """
    return (
        db.query(Baby)
        .filter(Baby.user_id == current_user.id)
        .order_by(Baby.created_at.asc())
        .all()
    )


@router.get("/{baby_id}", response_model=BabyResponse, summary="获取宝宝档案详情")
def get_baby(
    baby_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Baby:
    """查询单个宝宝档案（校验归属）。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 宝宝档案
    @raises NotFoundError: 档案不存在或不属于当前用户
    """
    return get_baby_or_404(baby_id, db, current_user.id)


@router.get("/{baby_id}/summary", response_model=GrowthSummary, summary="获取成长印记数据")
def get_baby_summary(
    baby_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GrowthSummary:
    """获取成长印记聚合数据（首页核心视觉：月龄、阶段、最近测量、里程碑进度）。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 成长印记聚合数据
    """
    baby = get_baby_or_404(baby_id, db, current_user.id)
    return build_growth_summary(db, baby)


@router.put("/{baby_id}", response_model=BabyResponse, summary="更新宝宝档案")
def update_baby(
    baby_id: int,
    payload: BabyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Baby:
    """更新宝宝档案信息。

    @param baby_id: 宝宝档案 ID
    @param payload: 更新字段
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 更新后的宝宝档案
    """
    baby = get_baby_or_404(baby_id, db, current_user.id)
    if payload.name is not None:
        baby.name = payload.name
    if payload.gender is not None:
        baby.gender = payload.gender
    if payload.birth_date is not None:
        baby.birth_date = payload.birth_date
    if payload.avatar_url is not None:
        baby.avatar_url = payload.avatar_url
    if payload.is_default:
        # 设为默认时，取消其他档案的默认标记
        db.query(Baby).filter(Baby.user_id == current_user.id, Baby.is_default.is_(True)).update(
            {Baby.is_default: False}
        )
        baby.is_default = True
    db.commit()
    db.refresh(baby)
    return baby


@router.delete("/{baby_id}", summary="删除宝宝档案")
def delete_baby(
    baby_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """删除宝宝档案（级联删除其全部记录）。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 删除结果提示
    """
    baby = get_baby_or_404(baby_id, db, current_user.id)
    db.delete(baby)
    db.commit()
    return {"deleted": True}
