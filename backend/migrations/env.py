"""
@file: migrations/env.py
@description: Alembic 迁移运行环境。确定迁移目标元数据（app.models 的 Base.metadata，
             共 12 张业务表）与数据库连接 URL，并支持 offline / online 两种执行模式。

URL 注入优先级（用于测试 / 多环境覆盖，Settings 为 lru_cache 单例难以运行时替换）：
1. 命令行参数：alembic -x db_url=sqlite:///... upgrade head
2. 程序化注入：alembic_cfg.attributes["db_url"] = "..."
   （见 app/main.py 生产启动与 tests/test_migrations.py 迁移测试）
3. 回落默认：app.core.config.settings.DATABASE_URL（从 .env / 环境变量加载）
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 将 backend/ 目录加入 sys.path，保证命令行在任意工作目录执行 alembic 时均可导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401  显式导入全部模型模块，确保表注册到 Base.metadata
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402

# Alembic Config 对象：提供对 alembic.ini 各配置段的访问
config = context.config

# 按 alembic.ini 的 [logger_*] 段配置迁移日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 迁移目标元数据：包含全部 12 张业务表（users/babies/growth_records/...）
target_metadata = Base.metadata


def _resolve_db_url() -> str:
    """解析本次迁移使用的数据库连接 URL。

    优先级：-x db_url 命令行参数 > config.attributes["db_url"] 注入 > settings.DATABASE_URL。

    @return: SQLAlchemy 连接 URL 字符串
    """
    # 1) 命令行 -x db_url=... 注入（alembic 1.19+ 中 get_x_argument 位于 EnvironmentContext）
    x_args = context.get_x_argument(as_dictionary=True)
    injected = x_args.get("db_url")
    if injected:
        return injected
    # 2) 进程内通过 alembic.command API 调用时以 attributes 注入
    attr_url = config.attributes.get("db_url")
    if attr_url:
        return attr_url
    # 3) 回落到应用全局配置（.env / 环境变量加载）
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """以 offline 模式执行迁移：不连接数据库，仅生成 SQL 脚本输出到标准输出。

    适用于 DBA 审核场景，如：alembic upgrade head --sql。

    @return: 无返回值
    """
    context.configure(
        url=_resolve_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以 online 模式执行迁移：连接数据库并在事务中执行迁移脚本。

    @return: 无返回值
    """
    # 以 alembic.ini 的 [alembic] 段为基础，注入解析后的真实连接 URL
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_db_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
