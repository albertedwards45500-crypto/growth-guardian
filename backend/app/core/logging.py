"""
@file: app/core/logging.py
@description: 日志系统配置。提供控制台与滚动文件双输出，日志按天滚动并保留 30 天。
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings


def setup_logging() -> None:
    """初始化应用日志配置。

    根日志器命名空间为 baby_growth：控制台输出便于开发观察，
    文件按天滚动保留 30 天，便于生产环境排障。

    @return: 无返回值
    """
    logger = logging.getLogger("baby_growth")
    if logger.handlers:
        # 已初始化过则跳过，避免重复添加 handler
        return

    logger.setLevel(settings.LOG_LEVEL.upper())

    # 统一的日志格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 滚动文件输出（每天一个文件，保留 30 天）
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=log_dir / "app.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 关闭日志向上传播，避免重复打印
    logger.propagate = False
