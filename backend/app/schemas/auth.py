"""
@file: app/schemas/auth.py
@description: 认证相关 Pydantic Schema：注册、登录与令牌响应。
"""

import re

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    """注册请求模型。

    @param phone: 手机号
    @param password: 密码（至少 6 位）
    @param nickname: 昵称（可选）
    """

    phone: str = Field(..., description="手机号")
    password: str = Field(..., min_length=6, max_length=64, description="密码，6-64位")
    nickname: str | None = Field(None, max_length=50, description="昵称")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """校验手机号格式（中国大陆 11 位手机号）。

        @param v: 手机号输入
        @return: 校验通过的原值
        @raises ValueError: 格式不正确时抛出
        """
        if not re.fullmatch(r"1[3-9]\d{9}", v):
            raise ValueError("手机号格式不正确")
        return v


class LoginRequest(BaseModel):
    """登录请求模型。"""

    phone: str = Field(..., description="手机号")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """登录成功后的令牌响应。"""

    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = "bearer"
    expires_in: int = Field(..., description="有效期（秒）")
