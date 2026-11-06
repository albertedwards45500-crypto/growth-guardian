"""
@file: tests/test_system.py
@description: 系统工具接口（一键测试）集成测试。使用假执行器注入 TaskManager，
             验证任务创建、状态轮询、失败结果与 404 场景，不真正嵌套运行 pytest。
"""

import time

import pytest

from app.api.v1 import system as system_api
from app.services.test_runner import TaskManager


class FakeRunner:
    """假测试执行器：立即返回预设结果，避免嵌套执行真实 pytest。

    @param result: 预设的测试结果字典
    """

    def __init__(self, result: dict) -> None:
        self.result = result

    def run(self) -> dict:
        return self.result


SUCCESS_RESULT = {
    "tests": 2,
    "passed": 2,
    "failed": 0,
    "errors": 0,
    "skipped": 0,
    "duration": 0.01,
    "failures": [],
}

FAILED_RESULT = {
    "tests": 2,
    "passed": 1,
    "failed": 1,
    "errors": 0,
    "skipped": 0,
    "duration": 0.01,
    "failures": [{"name": "test_math", "message": "assert 1 == 2"}],
}


@pytest.fixture()
def fake_manager(monkeypatch):
    """将 system 路由使用的管理器替换为注入假执行器的 TaskManager。

    @param monkeypatch: pytest 注入工具
    @return: TaskManager 实例（测试后自动还原）
    """

    def _install(result: dict) -> TaskManager:
        manager = TaskManager(runner=FakeRunner(result))
        monkeypatch.setattr(system_api, "manager", manager)
        return manager

    return _install


def _wait_done(client, task_id: str) -> dict:
    """轮询任务直至进入终态并返回任务数据。

    @param client: 测试客户端
    @param task_id: 任务 ID
    @return: 任务数据字典
    """
    task = None
    for _ in range(20):
        resp = client.get(f"/api/v1/system/test-tasks/{task_id}")
        assert resp.status_code == 200
        task = resp.json()["data"]
        if task["status"] in ("success", "failed"):
            return task
        time.sleep(0.05)
    raise AssertionError("任务未在预期时间内完成")


def test_run_tests_creates_task(client, fake_manager):
    """启动测试应立即返回任务 ID 与运行中状态。"""
    fake_manager(SUCCESS_RESULT)
    resp = client.post("/api/v1/system/run-tests")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["task_id"]
    assert data["status"] == "running"


def test_poll_task_success(client, fake_manager):
    """测试全部通过时，任务终态应为 success 且带统计结果。"""
    fake_manager(SUCCESS_RESULT)
    task_id = client.post("/api/v1/system/run-tests").json()["data"]["task_id"]
    task = _wait_done(client, task_id)
    assert task["status"] == "success"
    assert task["result"]["tests"] == 2
    assert task["result"]["passed"] == 2
    assert task["result"]["failed"] == 0


def test_poll_task_failed(client, fake_manager):
    """存在失败用例时，任务终态应为 failed 且携带失败明细。"""
    fake_manager(FAILED_RESULT)
    task_id = client.post("/api/v1/system/run-tests").json()["data"]["task_id"]
    task = _wait_done(client, task_id)
    assert task["status"] == "failed"
    assert task["result"]["failed"] == 1
    assert task["result"]["failures"][0]["name"] == "test_math"


def test_task_not_found(client):
    """查询不存在的任务应返回 404。"""
    resp = client.get("/api/v1/system/test-tasks/not-exist-id")
    assert resp.status_code == 404


def test_debug_routes_registration_controlled_by_debug_flag():
    """system 路由注册逻辑应受 DEBUG 开关控制：DEBUG=True 注册，False 不注册。

    应用级 DEBUG 在 create_app 时固化，这里直接以注册辅助函数分别构建两个
    轻量应用实例，通过 openapi paths 对比路由差异，验证条件注册逻辑。
    """
    from fastapi import FastAPI

    from app.main import register_debug_routes

    app_with_debug = FastAPI()
    app_without_debug = FastAPI()
    register_debug_routes(app_with_debug, debug=True)
    register_debug_routes(app_without_debug, debug=False)

    paths_with = set(app_with_debug.openapi()["paths"].keys())
    paths_without = set(app_without_debug.openapi()["paths"].keys())

    assert "/api/v1/system/run-tests" in paths_with
    assert "/api/v1/system/test-tasks/{task_id}" in paths_with
    assert "/api/v1/system/run-tests" not in paths_without
    assert "/api/v1/system/test-tasks/{task_id}" not in paths_without
