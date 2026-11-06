"""
@file: app/core/exceptions.py
@description: 统一业务异常体系。定义业务错误码、全局异常类及 FastAPI 异常处理器，
             保证所有接口返回统一格式的 JSON 响应。
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 获取应用日志器（与日志模块配合）
logger = logging.getLogger("baby_growth")


class BusinessError(Exception):
    """业务异常基类。

    携带业务码与用户可读的提示信息，由全局异常处理器统一转换为标准响应。

    @param code: 业务错误码（非 0）
    @param message: 面向用户的错误提示
    @param details: 附加详情（可选）
    """

    def __init__(self, code: int = 40000, message: str = "业务处理失败", details: Any = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(BusinessError):
    """资源不存在异常。"""

    def __init__(self, message: str = "请求的资源不存在"):
        super().__init__(code=40400, message=message)


class UnauthorizedError(BusinessError):
    """未认证/令牌失效异常。"""

    def __init__(self, message: str = "请先登录"):
        super().__init__(code=40100, message=message)


class ForbiddenError(BusinessError):
    """无权限操作异常。"""

    def __init__(self, message: str = "没有权限执行该操作"):
        super().__init__(code=40300, message=message)


class ConflictError(BusinessError):
    """资源冲突异常（如重复注册）。"""

    def __init__(self, message: str = "资源冲突"):
        super().__init__(code=40900, message=message)


def _build_response(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """构造统一响应体结构。

    @param code: 业务码，0 表示成功
    @param message: 提示文案
    @param data: 业务数据
    @return: 统一响应字典
    """
    return {"code": code, "message": message, "data": data}


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册全局异常处理器。

    @param app: FastAPI 应用实例
    @return: 无返回值，副作用为注册异常处理器
    """

    @app.exception_handler(BusinessError)
    async def business_error_handler(_: Request, exc: BusinessError) -> JSONResponse:
        """处理业务异常，返回统一业务错误码。"""
        logger.warning("业务异常 code=%s message=%s", exc.code, exc.message)
        return JSONResponse(
            status_code=200,  # 业务错误使用 200 + code 标识，便于前端统一处理
            content=_build_response(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        """处理请求参数校验失败，提取首个错误信息返回。"""
        first_error = exc.errors()[0] if exc.errors() else {}
        field = first_error.get("loc", ["body"])
        msg = first_error.get("msg", "参数校验失败")
        logger.warning("参数校验失败 field=%s msg=%s", field, msg)
        return JSONResponse(
            status_code=200,
            content=_build_response(42200, f"参数校验失败：{field[-1]} {msg}"),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        """兜底处理未捕获异常，记录日志并返回统一错误。"""
        logger.exception("未捕获异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_build_response(50000, "服务器内部错误，请稍后重试"),
        )
