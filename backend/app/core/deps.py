"""
@file: app/core/deps.py
@description: 通用依赖注入工具，提供当前认证用户、宝宝归属校验等公共依赖。
"""

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import SecurityError, decode_access_token
from app.models.baby import Baby
from app.models.user import User

# 安全的 Bearer 认证方案：auto_error=False 以便自行控制错误响应格式
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    """依赖：解析请求令牌并返回当前登录用户。

    @param db: 数据库会话
    @param credentials: HTTP Bearer 凭证（Authorization 头）
    @return: 当前用户 ORM 实例
    @raises UnauthorizedError: 令牌缺失或无效时抛出
    @raises NotFoundError: 用户不存在时抛出
    """
    if credentials is None:
        raise UnauthorizedError("请先登录")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub", "0"))
    except (SecurityError, ValueError) as exc:
        raise UnauthorizedError(str(exc)) from exc

    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    return user


def get_baby_or_404(baby_id: int, db: Session, user_id: int) -> Baby:
    """查询宝宝档案并校验归属当前用户。

    @param baby_id: 宝宝档案 ID
    @param db: 数据库会话
    @param user_id: 当前用户 ID
    @return: 宝宝 ORM 实例
    @raises NotFoundError: 档案不存在或不属于当前用户时抛出
    """
    baby = db.query(Baby).filter(Baby.id == baby_id, Baby.user_id == user_id).first()
    if baby is None:
        raise NotFoundError("宝宝档案不存在")
    return baby
