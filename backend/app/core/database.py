"""
@file: app/core/database.py
@description: 数据库引擎与会话管理。提供 SQLAlchemy 2.x 引擎、会话工厂及 FastAPI 依赖注入函数。
"""

import json
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""


def _json_serializer(obj) -> str:
    """JSON 序列化器：关闭 ASCII 转义并输出无空格紧凑格式。

    - ensure_ascii=False：保证中文原文存储，可被 LIKE 检索；
    - separators=(",", ":")：紧凑序列化（无 ", "/": " 空格），统一 SQLite
      （TEXT 原样存储）与 MySQL（JSON 类型文本化）两侧的存储文本形态，
      作为 services/recipe.py 过敏食材 LIKE 下推过滤的模式匹配前提：
      食材名在 JSON 中始终以 `"名称"`（两侧紧贴双引号）形式出现。

    @param obj: 待序列化对象
    @return: JSON 字符串
    """
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _json_deserializer(raw: str | bytes):
    """JSON 反序列化器。

    @param raw: JSON 字符串或字节
    @return: 反序列化后的 Python 对象
    """
    return json.loads(raw)


def _build_engine():
    """根据配置创建数据库引擎。

    MySQL 生产/开发场景开启连接池；SQLite 测试场景关闭检查器线程以避免跨线程问题。
    统一使用 ensure_ascii=False 的 JSON 序列化，保证中文文本可检索。

    @return: SQLAlchemy Engine 实例
    """
    common = {
        "pool_pre_ping": True,
        "json_serializer": _json_serializer,
        "json_deserializer": _json_deserializer,
    }
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url == "sqlite://":
            # 内存数据库：使用 StaticPool 保证所有连接共享同一内存库
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **common, **kwargs)
    return create_engine(
        url,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        echo=settings.DEBUG,
        **common,
    )


# 模块级引擎与会话工厂
engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供请求级别的数据库会话，并在请求结束时关闭。

    @yield: SQLAlchemy Session
    @raises: 会话操作异常由上层统一异常处理器捕获
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
