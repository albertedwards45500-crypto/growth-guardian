"""
@file: app/core/rate_limit.py
@description: 内存登录失败限流器。针对同一手机号连续登录失败达到阈值后锁定一段时间，
             防止暴力破解。基于 threading.Lock + dict 实现，线程安全，适用于单进程部署；
             多副本/分布式部署时应替换为 Redis 等共享存储实现。
"""

import threading
import time

# ---- 锁定规则常量 ----
# 说明：为避免与 config.py 并行修改冲突，暂定义在模块级；后续可移入 app/core/config.py 统一配置
LOGIN_MAX_FAILURES: int = 5  # 连续失败达到该次数即触发锁定
LOGIN_LOCK_MINUTES: int = 15  # 锁定持续时长（分钟）

# 限流记录存储：phone -> {"failures": int, "locked_until": float | None}
# failures: 连续失败次数；locked_until: 锁定到期时间戳（time.monotonic 秒），None 表示未锁定
_records: dict[str, dict] = {}
_lock = threading.Lock()


def record_failure(
    phone: str,
    max_failures: int = LOGIN_MAX_FAILURES,
    lock_minutes: int | float = LOGIN_LOCK_MINUTES,
) -> None:
    """记录一次登录失败；连续失败达到阈值时启动（或续期）锁定计时。

    @param phone: 登录手机号
    @param max_failures: 触发锁定的连续失败次数阈值（默认取模块常量，可注入覆盖便于测试）
    @param lock_minutes: 锁定持续时长（分钟，支持小数；默认取模块常量，可注入覆盖便于测试）
    @return: 无返回值，副作用为更新内存中的失败计数与锁定到期时间
    """
    with _lock:
        now = time.monotonic()
        record = _records.get(phone)
        # 惰性清理：该手机号上次锁定已到期则重置计数重新累计
        if (
            record is not None
            and record["locked_until"] is not None
            and now >= record["locked_until"]
        ):
            record = None
            _records.pop(phone, None)
        if record is None:
            record = {"failures": 0, "locked_until": None}
            _records[phone] = record

        record["failures"] += 1
        if record["failures"] >= max_failures:
            record["locked_until"] = now + lock_minutes * 60


def is_locked(
    phone: str,
    max_failures: int = LOGIN_MAX_FAILURES,
    lock_minutes: int | float = LOGIN_LOCK_MINUTES,
) -> bool:
    """判断该手机号当前是否处于登录锁定状态；锁定到期时惰性清理记录。

    @param phone: 登录手机号
    @param max_failures: 失败次数阈值（保留注入参数，锁定判定以记录内的 locked_until 为准）
    @param lock_minutes: 锁定时长（保留注入参数，锁定判定以记录内的 locked_until 为准）
    @return: 处于锁定期内返回 True；未锁定或锁定已到期返回 False
    """
    with _lock:
        record = _records.get(phone)
        if record is None:
            return False
        locked_until = record["locked_until"]
        if locked_until is None:
            return False
        if time.monotonic() >= locked_until:
            # 锁定已到期：惰性清理该条目，恢复可登录并重新计数
            _records.pop(phone, None)
            return False
        return True


def clear(phone: str) -> None:
    """清除指定手机号的失败记录（登录成功后调用）。

    @param phone: 登录手机号
    @return: 无返回值，副作用为删除该手机号的限流记录
    """
    with _lock:
        _records.pop(phone, None)


def reset() -> None:
    """清空全部限流记录（供测试隔离与运维重置使用）。

    @return: 无返回值，副作用为清空内存记录字典
    """
    with _lock:
        _records.clear()
