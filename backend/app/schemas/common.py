"""
@file: app/schemas/common.py
@description: 通用 Pydantic Schema：统一响应包装与分页模型。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

# 业务数据类型泛型变量
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应包装。

    @param code: 业务码，0 表示成功
    @param message: 提示信息
    @param data: 业务数据
    """

    code: int = 0
    message: str = "ok"
    data: T | None = None


class PageResult(BaseModel, Generic[T]):
    """分页结果模型。

    @param items: 当前页数据
    @param total: 总条数
    @param page: 当前页码（从 1 开始）
    @param page_size: 每页条数
    """

    items: list[T]
    total: int
    page: int
    page_size: int
