"""
@file: tests/conftest.py
@description: pytest 公共夹具。使用独立 SQLite 内存库，提供已登录客户端、
             登录令牌与演示数据等辅助工具。
"""

import os

# 必须在导入 app 之前覆盖数据库配置，确保测试使用独立 SQLite 内存库
os.environ["DATABASE_URL"] = "sqlite://"
# 测试密钥长度 >= 32 字节，避免触发 PyJWT 的 InsecureKeyLengthWarning
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-0123456789abcdef"
# 测试环境开启 DEBUG，保证 /api/v1/system 一键测试路由已注册（与开发环境行为一致）
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"
# 默认测试绝不读取开发者的模型开关、密钥或真实向量目录；集成用例显式注入假服务。
os.environ["ADVISOR_AGENT_ENABLED"] = "false"
os.environ["RAG_ENABLED"] = "false"
os.environ["RAG_RETRIEVAL_STRATEGY"] = "baseline"
os.environ["RAG_CANDIDATE_TOP_K"] = "5"
os.environ["RAG_CANDIDATE_MIN_SCORE"] = "0.45"
os.environ["RAG_LEXICAL_SCAN_LIMIT"] = "200"
os.environ["OPENAI_API_KEY"] = ""
os.environ["RAG_EMBEDDING_API_KEY"] = ""
os.environ["RAG_EMBEDDING_SEND_DIMENSIONS"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

# 测试账号
TEST_PHONE = "13900000001"
TEST_PASSWORD = "test123456"


@pytest.fixture(scope="session", autouse=True)
def prepare_db():
    """会话级夹具：建表并运行种子数据（内存库随进程回收，无需清理）。

    @yield: 无返回值
    """
    Base.metadata.create_all(bind=engine)
    from app.seed.init_seed import seed_all

    seed_all()
    yield


@pytest.fixture(autouse=True)
def reset_login_rate_limit():
    """每个用例前清空登录失败限流记录，保证用例间状态隔离。

    @yield: 无返回值
    """
    from app.core import rate_limit

    rate_limit.reset()
    yield


@pytest.fixture()
def client():
    """提供基于测试库的 HTTP 客户端（自动触发应用生命周期）。

    @yield: TestClient 实例
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client) -> dict:
    """注册并登录测试用户，返回鉴权请求头。

    @param client: 测试客户端
    @return: {"Authorization": "Bearer <token>"}
    """
    # 幂等注册：已存在则直接登录
    client.post(
        "/api/v1/auth/register",
        json={"phone": TEST_PHONE, "password": TEST_PASSWORD, "nickname": "测试家长"},
    )
    login = client.post(
        "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": TEST_PASSWORD}
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def demo_headers(client) -> dict:
    """使用内置演示账号（13800000000/123456）的请求头，含演示宝宝数据。

    @param client: 测试客户端
    @return: {"Authorization": "Bearer <token>"}
    """
    login = client.post(
        "/api/v1/auth/login", json={"phone": "13800000000", "password": "123456"}
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_test_baby(client, headers: dict, name: str = "安安") -> dict:
    """创建测试宝宝档案并返回响应数据。

    @param client: 测试客户端
    @param headers: 鉴权头
    @param name: 宝宝昵称
    @return: 创建成功后的宝宝数据字典
    """
    resp = client.post(
        "/api/v1/babies",
        headers=headers,
        json={"name": name, "gender": "female", "birth_date": "2026-02-01"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]
