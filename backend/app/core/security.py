"""
@file: app/core/security.py
@description: 安全工具模块，提供密码哈希校验与 JWT 令牌签发/解析能力。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


class SecurityError(Exception):
    """安全相关自定义异常，用于令牌解析失败等场景。"""


def hash_password(plain_password: str) -> str:
    """使用 bcrypt 对明文密码进行加盐哈希。

    @param plain_password: 用户明文密码
    @return: 哈希后的密码字符串
    @raises ValueError: 明文密码为空时抛出
    """
    if not plain_password:
        raise ValueError("密码不能为空")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希密码是否匹配。

    @param plain_password: 用户输入的明文密码
    @param hashed_password: 数据库中存储的哈希密码
    @return: 匹配返回 True，否则返回 False
    """
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # 数据库中的哈希格式异常时按不匹配处理
        return False


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    """签发 JWT 访问令牌。

    @param subject: 令牌主体，通常为用户 ID
    @param expires_minutes: 有效期（分钟），默认取配置值
    @return: 编码后的 JWT 字符串
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """解析并校验 JWT 令牌。

    @param token: JWT 字符串
    @return: 解码后的载荷字典
    @raises SecurityError: 令牌无效、过期或签名错误时抛出
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise SecurityError("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise SecurityError("无效的登录凭证") from exc
