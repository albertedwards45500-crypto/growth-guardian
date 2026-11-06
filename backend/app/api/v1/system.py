"""
@file: app/api/v1/system.py
@description: 系统工具接口：提供"一键启动测试"能力（创建测试任务 + 轮询任务状态）。
             该接口面向开发与内部环境，不要求用户认证。
"""

from fastapi import APIRouter, HTTPException

from app.services.test_runner import manager

router = APIRouter(prefix="/system", tags=["系统工具"])


@router.post("/run-tests", response_model=dict, summary="一键启动测试")
def run_tests() -> dict:
    """创建测试任务并立即后台执行完整测试套件。

    @return: 任务摘要（task_id 与 status=running），供前端轮询
    """
    return manager.start()


@router.get("/test-tasks/{task_id}", response_model=dict, summary="查询测试任务状态")
def get_test_task(task_id: str) -> dict:
    """按任务 ID 查询测试执行状态与结果。

    @param task_id: 测试任务 ID
    @return: 任务数据（含 status 与完成后的 result）
    @raises HTTPException: 任务不存在时返回 404
    """
    task = manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="测试任务不存在")
    return task
