"""
@file: app/api/v1/auth.py
@description: 认证接口：用户注册与登录。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BusinessError, ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserProfile

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=UserProfile, summary="用户注册")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    """注册新用户。

    @param payload: 注册请求（手机号、密码、昵称）
    @param db: 数据库会话
    @return: 新用户资料
    @raises ConflictError: 手机号已注册时抛出
    """
    exists = db.query(User).filter(User.phone == payload.phone).first()
    if exists:
        raise ConflictError("该手机号已注册，请直接登录")

    user = User(
        phone=payload.phone,
        nickname=payload.nickname or "家长",
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """手机号密码登录，签发 JWT 访问令牌。

    @param payload: 登录请求（手机号、密码）
    @param db: 数据库会话
    @return: 访问令牌与有效期
    @raises BusinessError: 连续登录失败触发限流锁定时抛出（code=42900）
    @raises UnauthorizedError: 账号不存在或密码错误时抛出
    """
    # 登录失败限流：锁定期间直接拒绝，防止暴力破解
    if rate_limit.is_locked(payload.phone):
        raise BusinessError(code=42900, message="登录失败次数过多，请15分钟后重试")

    user = db.query(User).filter(User.phone == payload.phone).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        rate_limit.record_failure(payload.phone)
        raise UnauthorizedError("手机号或密码错误")

    rate_limit.clear(payload.phone)
    expires_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    token = create_access_token(user.id, expires_minutes=expires_minutes)
    return TokenResponse(access_token=token, expires_in=expires_minutes * 60)
