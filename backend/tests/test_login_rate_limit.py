"""
@file: tests/test_login_rate_limit.py
@description: 登录失败限流测试。集成级验证连续失败锁定与 reset 解锁（TestClient），
             单元级通过注入 max_failures / lock_minutes 覆盖参数验证锁定阈值与到期自动解锁。
"""

import time

from app.core import rate_limit
from tests.conftest import TEST_PASSWORD, TEST_PHONE


class TestLoginRateLimitApi:
    """登录接口限流集成测试组（基于 TestClient）。"""

    def test_lock_after_five_failures(self, client):
        """连续 5 次错误密码后，第 6 次即使密码正确也应返回 42900。"""
        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": "wrong-pass"}
            )
            assert resp.json()["code"] == 40100

        resp = client.post(
            "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 42900
        assert "登录失败次数过多" in body["message"]

    def test_reset_allows_login(self, client):
        """触发锁定后调用 reset 清空记录，应可重新正常登录。"""
        for _ in range(5):
            client.post(
                "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": "wrong-pass"}
            )
        assert client.post(
            "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": TEST_PASSWORD}
        ).json()["code"] == 42900

        rate_limit.reset()
        resp = client.post(
            "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": TEST_PASSWORD}
        )
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["access_token"]


class TestRateLimitUnit:
    """限流器单元测试组（直接调用注入参数验证规则）。"""

    def test_injected_max_failures_triggers_lock(self):
        """注入 max_failures=2 时，连续失败 2 次即应进入锁定状态。"""
        phone = "13811112222"
        rate_limit.record_failure(phone, max_failures=2)
        assert rate_limit.is_locked(phone) is False

        rate_limit.record_failure(phone, max_failures=2)
        assert rate_limit.is_locked(phone) is True

    def test_lock_expires_with_injected_short_lock(self):
        """注入极短 lock_minutes 验证锁定到期后自动解锁并重新计数。"""
        phone = "13811113333"
        for _ in range(5):
            rate_limit.record_failure(phone, lock_minutes=0.001)  # 0.001 分钟 ≈ 0.06 秒
        assert rate_limit.is_locked(phone) is True

        time.sleep(0.1)  # 等待锁定到期
        assert rate_limit.is_locked(phone) is False

        # 到期解锁后计数应重新累计：失败 1 次不应立即锁定
        rate_limit.record_failure(phone)
        assert rate_limit.is_locked(phone) is False

    def test_clear_and_reset(self):
        """clear 应清除指定手机号记录，reset 应清空全部记录。"""
        rate_limit.record_failure("13811114444", max_failures=1)
        rate_limit.record_failure("13811115555", max_failures=1)
        assert rate_limit.is_locked("13811114444") is True
        assert rate_limit.is_locked("13811115555") is True

        rate_limit.clear("13811114444")
        assert rate_limit.is_locked("13811114444") is False
        assert rate_limit.is_locked("13811115555") is True

        rate_limit.reset()
        assert rate_limit.is_locked("13811115555") is False
