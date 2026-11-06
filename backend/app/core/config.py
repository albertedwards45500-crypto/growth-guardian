"""
@file: app/core/config.py
@description: 全局配置模块，基于 pydantic-settings 从环境变量 / .env 文件加载配置。
             覆盖数据库连接、JWT 安全、跨域、日志等运行参数。
             所有默认值均为脱敏占位符：生产环境（DEBUG=False）启动时会执行
             validate_production_config 强校验，凭据必须通过环境变量注入。
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/）
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 已知不安全的默认 SECRET_KEY 值，生产环境禁止使用
_KNOWN_DEFAULT_SECRET_KEY = "change-me-in-production-9f8e7d6c5b4a3"
# 数据库连接串中的占位口令标识，出现即说明真实凭据未被注入
_DB_PASSWORD_PLACEHOLDER = "change-me-db-password"
# root 弱口令连接模式标识（如 mysql+pymysql://root:xxxx@...）
_ROOT_WEAK_CREDENTIAL_PATTERN = "root:"


class Settings(BaseSettings):
    """应用全局配置类。

    属性均可在 .env 文件中覆盖，字段说明见各注释。
    """

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用基本信息 ----
    APP_NAME: str = "宝宝辅食与成长记录 - 后端服务"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ---- 数据库连接 ----
    # 默认值为脱敏占位连接串：生产环境必须通过环境变量注入真实凭据，
    # 禁止将真实口令写入仓库；测试环境可覆盖为 SQLite（见 tests/conftest.py）
    DATABASE_URL: str = "mysql+pymysql://baby_user:change-me-db-password@127.0.0.1:3306/baby_growth?charset=utf8mb4"

    # ---- JWT 安全配置 ----
    # SECRET_KEY 生产环境必须通过环境变量注入，禁止提交真实密钥
    SECRET_KEY: str = "change-me-in-production-9f8e7d6c5b4a3"
    ALGORITHM: str = "HS256"
    # 访问令牌有效期（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # ---- CORS 跨域配置 ----
    # 允许的前端来源，逗号分隔
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- 日志配置 ----
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = str(BASE_DIR / "logs")

    # 显式启用才向配置的模型服务发送提问和最小化工具数据。
    ADVISOR_AGENT_ENABLED: bool = False
    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ADVISOR_MODEL: str = ""
    ADVISOR_MODEL_TIMEOUT_SECONDS: float = Field(20, ge=1, le=60)
    ADVISOR_AGENT_MAX_ROUNDS: int = Field(3, ge=1, le=5)
    ADVISOR_AGENT_MAX_TOOL_CALLS: int = Field(6, ge=1, le=10)
    RAG_ENABLED: bool = False
    # Embedding 独立凭据，不回退到问答服务密钥，避免跨服务误用。
    RAG_EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    RAG_EMBEDDING_API_KEY: SecretStr = SecretStr("")
    RAG_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_EMBEDDING_DIMENSIONS: int = Field(1536, ge=1, le=3072)
    # 固定维度模型可能不接收 dimensions 参数；仍严格校验返回向量长度。
    RAG_EMBEDDING_SEND_DIMENSIONS: bool = True
    RAG_TOP_K: int = Field(3, ge=1, le=5)
    RAG_MIN_SCORE: float = Field(0.55, ge=0, le=1)
    # 默认保留原检索策略；候选池扩展须先隔离评估，不改变最终引用校验。
    RAG_RETRIEVAL_STRATEGY: Literal["baseline", "expanded", "hybrid"] = "baseline"
    RAG_CANDIDATE_TOP_K: int = Field(5, ge=1, le=5)
    RAG_CANDIDATE_MIN_SCORE: float = Field(0.45, ge=0, le=1)
    RAG_LEXICAL_SCAN_LIMIT: int = Field(200, ge=1, le=1000)
    QDRANT_PATH: str = str(BASE_DIR / "data" / "qdrant")
    # 留空使用本地持久化；多进程部署应指定独立 Qdrant 服务。
    QDRANT_URL: str = ""
    QDRANT_API_KEY: SecretStr = SecretStr("")
    QDRANT_COLLECTION: str = "reviewed_baby_knowledge_v1"

    @property
    def cors_origin_list(self) -> list[str]:
        """将逗号分隔的跨域来源字符串解析为列表。

        @return: CORS 允许来源列表
        """
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def validate_production_config(self) -> None:
        """校验生产环境配置的安全性（凭据不得为默认值/弱口令）。

        校验规则（仅 DEBUG=False 时强校验）：
        - SECRET_KEY 不得等于已知默认值，且长度不得小于 32 字符；
        - DATABASE_URL 不得包含占位口令，也不得使用 root 弱口令连接模式。

        DEBUG=True（开发/测试环境）时跳过强校验，仅输出告警日志。

        @return: 无返回值；校验通过时静默返回
        @raises RuntimeError: 生产配置不达标时抛出；错误消息只描述违规规则，
                 不回显实际配置值，避免敏感信息泄露到日志/控制台
        """
        if self.DEBUG:
            logging.getLogger("baby_growth").warning(
                "当前处于 DEBUG 模式，生产配置强校验已跳过，请勿以该配置上线"
            )
            return

        problems: list[str] = []
        if self.SECRET_KEY == _KNOWN_DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY 仍为已知默认值，必须替换为随机强密钥")
        elif len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY 长度不足 32 字符，密钥强度不达标")

        if _DB_PASSWORD_PLACEHOLDER in self.DATABASE_URL:
            problems.append("DATABASE_URL 仍包含占位口令，必须通过环境变量注入真实凭据")
        elif _ROOT_WEAK_CREDENTIAL_PATTERN in self.DATABASE_URL:
            problems.append("DATABASE_URL 使用 root 弱口令连接模式，必须改用独立业务账号")

        if problems:
            raise RuntimeError("生产配置校验失败：" + "；".join(problems))


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（带缓存，避免重复解析 .env）。

    @return: Settings 实例
    """
    return Settings()


# 模块级便捷引用
settings = get_settings()
