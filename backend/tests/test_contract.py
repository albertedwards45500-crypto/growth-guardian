"""
@file: tests/test_contract.py
@description: 错误契约集成测试与生产配置校验单测。
             契约：业务错误 = HTTP 200 + 业务码（40100/40300/40400/40900/42200），
             服务器未捕获异常 = HTTP 500 + 50000；响应统一为 {code, message, data}，
             且错误响应不得泄露敏感信息。
"""

import logging

import pytest

from app.core.config import Settings

# 注册接口完整字段（nickname 为可选），用于构造重复注册场景
REGISTER_FULL_PAYLOAD = {"phone": "13866660001", "password": "abc123456", "nickname": "契约测试"}

# 错误响应中禁止出现的敏感词（真实口令/弱口令账号/凭据字段名均不得外泄）
SENSITIVE_WORDS = ("root", "520118", "password")


class TestErrorContract:
    """错误契约集成测试组：业务错误统一返回 HTTP 200 + 业务码。"""

    def test_unauthorized_returns_200_with_40100(self, client):
        """未认证访问受保护接口应返回 HTTP 200 + code 40100。

        @param client: 测试客户端
        """
        resp = client.get("/api/v1/babies")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 40100
        # 响应必须包含统一结构的三要素
        for key in ("code", "message", "data"):
            assert key in body

    def test_unauthorized_response_shape_and_no_leak(self, client):
        """未认证错误响应顶层应仅含 code/message/data，且不含敏感词。

        @param client: 测试客户端
        """
        resp = client.get("/api/v1/babies")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data"}
        text = str(body).lower()
        for word in SENSITIVE_WORDS:
            assert word not in text

    def test_invalid_token_returns_40100(self, client):
        """携带无效令牌访问受保护接口应返回 HTTP 200 + code 40100。

        @param client: 测试客户端
        """
        resp = client.get(
            "/api/v1/babies", headers={"Authorization": "Bearer invalid-token"}
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 40100

    def test_duplicate_register_returns_40900(self, client):
        """重复注册同一手机号应返回 HTTP 200 + code 40900。

        @param client: 测试客户端
        """
        first = client.post("/api/v1/auth/register", json=REGISTER_FULL_PAYLOAD)
        assert first.status_code == 200
        assert first.json()["code"] == 0

        second = client.post("/api/v1/auth/register", json=REGISTER_FULL_PAYLOAD)
        assert second.status_code == 200
        body = second.json()
        assert body["code"] == 40900
        for key in ("code", "message", "data"):
            assert key in body

    def test_missing_field_returns_42200(self, client):
        """注册缺失必填字段（phone）应返回 HTTP 200 + code 42200（而非 HTTP 422）。

        仅传 password 缺失 phone：错误消息不包含凭据类字段名，便于统一断言敏感词。

        @param client: 测试客户端
        """
        resp = client.post("/api/v1/auth/register", json={"password": "abc123456"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 42200
        assert body["message"]
        for key in ("code", "message", "data"):
            assert key in body
        text = str(body).lower()
        for word in SENSITIVE_WORDS:
            assert word not in text


class TestProductionConfigValidation:
    """生产配置校验单测组：DEBUG=False 时强校验，DEBUG=True 时仅告警。"""

    @staticmethod
    def _make_settings(**kwargs) -> Settings:
        """构造与本地 .env 隔离的 Settings 实例（不读取 .env 文件）。

        @param kwargs: 覆盖的字段值（init 参数优先级最高，可屏蔽环境变量干扰）
        @return: 用于校验测试的 Settings 实例
        """
        return Settings(_env_file=None, **kwargs)

    def test_short_secret_key_raises(self):
        """DEBUG=False 且 SECRET_KEY 过短时应抛出 RuntimeError。

        @raises RuntimeError: 预期校验失败
        """
        s = self._make_settings(DEBUG=False, SECRET_KEY="short")
        with pytest.raises(RuntimeError):
            s.validate_production_config()

    def test_default_secret_key_raises(self):
        """DEBUG=False 且 SECRET_KEY 为已知默认值时应抛出 RuntimeError。

        @raises RuntimeError: 预期校验失败
        """
        s = self._make_settings(
            DEBUG=False,
            SECRET_KEY="change-me-in-production-9f8e7d6c5b4a3",
            DATABASE_URL="mysql+pymysql://baby_user:real-password@127.0.0.1:3306/db",
        )
        with pytest.raises(RuntimeError):
            s.validate_production_config()

    def test_placeholder_db_password_raises(self):
        """DEBUG=False 且 DATABASE_URL 含占位口令时应抛出 RuntimeError。

        @raises RuntimeError: 预期校验失败
        """
        s = self._make_settings(
            DEBUG=False,
            SECRET_KEY="x" * 32,
            DATABASE_URL="mysql+pymysql://baby_user:change-me-db-password@127.0.0.1:3306/db",
        )
        with pytest.raises(RuntimeError):
            s.validate_production_config()

    def test_root_weak_credential_raises(self):
        """DEBUG=False 且 DATABASE_URL 使用 root 弱口令模式时应抛出 RuntimeError。

        @raises RuntimeError: 预期校验失败
        """
        s = self._make_settings(
            DEBUG=False,
            SECRET_KEY="x" * 32,
            DATABASE_URL="mysql+pymysql://root:weak-password@127.0.0.1:3306/db",
        )
        with pytest.raises(RuntimeError):
            s.validate_production_config()

    def test_error_message_does_not_leak_value(self):
        """校验失败消息不得回显实际配置值，只描述违规规则。

        @raises RuntimeError: 预期校验失败
        """
        secret = "short-secret"
        s = self._make_settings(DEBUG=False, SECRET_KEY=secret)
        with pytest.raises(RuntimeError) as excinfo:
            s.validate_production_config()
        assert secret not in str(excinfo.value)

    def test_valid_production_config_passes(self):
        """DEBUG=False 且配置达标时应静默通过，不抛出任何异常。"""
        s = self._make_settings(
            DEBUG=False,
            SECRET_KEY="x" * 32,
            DATABASE_URL="mysql+pymysql://baby_user:strong-password@127.0.0.1:3306/db",
        )
        assert s.validate_production_config() is None

    def test_debug_true_only_warns(self, caplog):
        """DEBUG=True 时即使配置不达标也仅告警，不抛出异常。

        @param caplog: pytest 日志捕获夹具
        """
        s = self._make_settings(
            DEBUG=True,
            SECRET_KEY="short",
            DATABASE_URL="mysql+pymysql://root:weak@127.0.0.1/db",
        )
        with caplog.at_level(logging.WARNING, logger="baby_growth"):
            s.validate_production_config()  # 不应抛出
        assert any("DEBUG 模式" in r.message for r in caplog.records)
