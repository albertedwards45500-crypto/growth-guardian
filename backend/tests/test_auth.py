"""
@file: tests/test_auth.py
@description: 认证模块集成测试：注册、登录、鉴权与错误场景。
"""

from tests.conftest import TEST_PASSWORD, TEST_PHONE


class TestRegister:
    """注册接口测试组。"""

    def test_register_success(self, client):
        """注册新用户应成功并返回用户资料。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"phone": "13911112222", "password": "abc123", "nickname": "小美妈妈"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["phone"] == "13911112222"
        assert body["data"]["nickname"] == "小美妈妈"
        # 响应不应泄露密码哈希
        assert "password" not in body["data"]

    def test_register_duplicate_phone(self, client):
        """重复手机号注册应返回冲突错误码。"""
        # 幂等预注册：确保 TEST_PHONE 已存在（避免依赖其他测试文件的注册副作用）
        client.post(
            "/api/v1/auth/register",
            json={"phone": TEST_PHONE, "password": TEST_PASSWORD, "nickname": "测试家长"},
        )
        resp = client.post(
            "/api/v1/auth/register",
            json={"phone": TEST_PHONE, "password": TEST_PASSWORD},
        )
        body = resp.json()
        assert body["code"] == 40900

    def test_register_invalid_phone(self, client):
        """非法手机号应返回参数校验错误。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"phone": "12345", "password": "abc123"},
        )
        assert resp.json()["code"] == 42200

    def test_register_short_password(self, client):
        """过短密码应返回参数校验错误。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"phone": "13922223333", "password": "123"},
        )
        assert resp.json()["code"] == 42200


class TestLogin:
    """登录接口测试组。"""

    def test_login_success(self, client):
        """正确凭据登录应返回 JWT 令牌。"""
        resp = client.post(
            "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": TEST_PASSWORD}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_login_wrong_password(self, client):
        """错误密码应返回 40100 业务码。"""
        resp = client.post(
            "/api/v1/auth/login", json={"phone": TEST_PHONE, "password": "wrong-pass"}
        )
        assert resp.json()["code"] == 40100

    def test_login_unknown_user(self, client):
        """未注册手机号应返回 40100 业务码。"""
        resp = client.post(
            "/api/v1/auth/login", json={"phone": "13799999999", "password": "abc123"}
        )
        assert resp.json()["code"] == 40100


class TestAuthGuard:
    """鉴权守卫测试组。"""

    def test_access_without_token(self, client):
        """无令牌访问受保护接口应返回 40100。"""
        resp = client.get("/api/v1/babies")
        assert resp.json()["code"] == 40100

    def test_access_with_invalid_token(self, client):
        """无效令牌访问应返回 40100。"""
        resp = client.get("/api/v1/babies", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.json()["code"] == 40100

    def test_health_check(self, client):
        """健康检查接口无需鉴权。"""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
