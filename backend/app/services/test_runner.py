"""
@file: app/services/test_runner.py
@description: 测试执行服务。以后台线程方式运行 pytest 子进程，解析 junitxml 输出，
             并以任务字典形式向接口层提供状态查询能力（供"一键启动测试"功能使用）。
"""

import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR

# 任务状态常量
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


class TestRunner:
    """pytest 测试执行器：负责构建命令、运行子进程并解析结果。

    @method run: 同步执行测试并返回结构化结果
    """

    def run(self) -> dict:
        """执行完整测试套件并返回结构化结果。

        @return: 结果字典，含 tests/passed/failed/errors/skipped/duration/failures
        """
        # junitxml 报告写入临时文件，便于精确解析
        xml_path = Path(BASE_DIR) / f"test-report-{uuid.uuid4().hex[:8]}.xml"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(BASE_DIR / "pytest.ini"),
            "-q",
            "--tb=short",
            "--junitxml",
            str(xml_path),
        ]
        try:
            start = time.perf_counter()
            proc = subprocess.run(
                cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            duration = round(time.perf_counter() - start, 2)
            result = self._parse_junit(xml_path, proc, duration)
        finally:
            # 清理临时报告文件
            if xml_path.exists():
                xml_path.unlink(missing_ok=True)
        return result

    def _parse_junit(self, xml_path: Path, proc: subprocess.CompletedProcess, duration: float) -> dict:
        """解析 junitxml 报告并合并进程返回码，生成结构化测试结果。

        @param xml_path: junitxml 报告路径
        @param proc: pytest 子进程执行结果
        @param duration: 测试总耗时（秒）
        @return: 结构化测试结果
        """
        summary = {
            "tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration": duration,
            "failures": [],
        }
        if not xml_path.exists():
            # 报告缺失（如测试进程异常退出），退回解析 stdout 摘要
            summary["failures"].append({"name": "pytest", "message": (proc.stdout or proc.stderr)[-500:]})
            summary["failed"] = 1 if proc.returncode != 0 else 0
            return summary

        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError as exc:
            summary["failures"].append({"name": "pytest", "message": f"报告解析失败：{exc}"})
            summary["failed"] = 1
            return summary

        # 支持 <testsuites> 包裹多套件与直接 <testsuite> 两种形态
        suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
        for suite in suites:
            summary["tests"] += int(suite.attrib.get("tests", 0))
            summary["failed"] += int(suite.attrib.get("failures", 0))
            summary["errors"] += int(suite.attrib.get("errors", 0))
            summary["skipped"] += int(suite.attrib.get("skipped", 0))
            for case in suite.iter("testcase"):
                # 收集失败/错误用例明细
                issue = case.find("failure")
                if issue is None:
                    issue = case.find("error")
                if issue is not None:
                    summary["failures"].append(
                        {
                            "name": f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}",
                            "message": (issue.attrib.get("message") or issue.text or "")[:300],
                        }
                    )
        summary["passed"] = summary["tests"] - summary["failed"] - summary["errors"] - summary["skipped"]
        return summary


class TaskManager:
    """测试任务管理器：维护任务注册表，支持后台异步执行与状态查询。

    @method start: 创建并启动一个测试任务
    @method get: 按任务 ID 查询任务状态与结果
    """

    def __init__(self, runner: TestRunner | None = None) -> None:
        """初始化任务管理器。

        @param runner: 测试执行器，默认使用 TestRunner（测试时可注入 Mock）
        """
        self._runner = runner or TestRunner()
        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def start(self) -> dict:
        """创建测试任务并立即后台执行。

        @return: 任务摘要（task_id 与 status=running）
        """
        task_id = uuid.uuid4().hex
        task: dict[str, Any] = {
            "task_id": task_id,
            "status": STATUS_RUNNING,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "result": None,
        }
        with self._lock:
            self._tasks[task_id] = task
        # 后台线程执行测试，避免阻塞请求
        thread = threading.Thread(
            target=self._execute, args=(task_id,), name=f"test-runner-{task_id[:8]}", daemon=True
        )
        thread.start()
        return {"task_id": task_id, "status": STATUS_RUNNING}

    def get(self, task_id: str) -> dict | None:
        """查询任务状态。

        @param task_id: 任务 ID
        @return: 任务数据；不存在时返回 None
        """
        with self._lock:
            return self._tasks.get(task_id)

    def _execute(self, task_id: str) -> None:
        """后台执行测试并回写结果（线程入口）。

        @param task_id: 任务 ID
        """
        task = self.get(task_id)
        if task is None:
            return
        try:
            result = self._runner.run()
        except Exception as exc:  # 兜底：执行异常视为失败
            result = {
                "tests": 0,
                "passed": 0,
                "failed": 1,
                "errors": 0,
                "skipped": 0,
                "duration": 0,
                "failures": [{"name": "runner", "message": str(exc)[:300]}],
            }
        with self._lock:
            task["finished_at"] = datetime.now().isoformat(timespec="seconds")
            task["result"] = result
            task["status"] = STATUS_SUCCESS if result["failed"] == 0 and result["errors"] == 0 else STATUS_FAILED


# 模块级单例，供接口层与测试复用
manager = TaskManager()
