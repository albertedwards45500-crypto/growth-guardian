"""
@file: tests/test_security.py
@description: 安全专项测试：跨用户越权矩阵、敏感信息泄露防护、CORS 白名单与
             登录限流器多线程并发安全。
             与既有测试分工：test_contract.py 覆盖错误契约与生产配置校验、
             test_login_rate_limit.py 覆盖限流锁定/解锁规则，本文件不重复其断言。
"""

import json
import threading

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.config import settings
from app.main import app

# 越权场景专用账号（与其他测试文件手机号隔离，避免数据串扰）
PHONE_OWNER = "13900000311"
PHONE_ATTACKER = "13900000312"
PHONE_LEAK_A = "13900000321"
PHONE_LEAK_B = "13900000322"
SEC_PASSWORD = "sec123456"

# 越权矩阵：访客 B 以 (方法, 路径模板, 请求体) 访问属主 A 的各类资源。
# 各端点归属校验语义统一（get_baby_or_404 / user_id 过滤）→ 全部返回 40400，
# 不泄露"资源存在但不属于你"的信息。
CROSS_ACCESS_CASES = [
    ("GET", "/api/v1/babies/{baby_id}", None),
    ("PUT", "/api/v1/babies/{baby_id}", {"name": "被篡改的名字"}),
    ("DELETE", "/api/v1/babies/{baby_id}", None),
    ("GET", "/api/v1/babies/{baby_id}/summary", None),
    ("GET", "/api/v1/babies/{baby_id}/growth-curve", None),
    ("GET", "/api/v1/babies/{baby_id}/growth-records", None),
    (
        "POST",
        "/api/v1/babies/{baby_id}/growth-records",
        {"record_date": "2026-09-01", "weight_kg": 7.0},
    ),
    (
        "POST",
        "/api/v1/babies/{baby_id}/milestones",
        {"milestone_type": "walk", "name": "行走", "achieved_at": "2026-09-01"},
    ),
    (
        "POST",
        "/api/v1/babies/{baby_id}/diet-records",
        {"record_date": "2026-09-01", "record_type": "formula", "details": {"amount_ml": 60}},
    ),
    ("POST", "/api/v1/babies/{baby_id}/allergies", {"ingredient": "花生"}),
    ("GET", "/api/v1/babies/{baby_id}/meal-plans?week_start=2026-08-03", None),
    ("PUT", "/api/v1/babies/{baby_id}/meal-plans", {"week_start": "2026-08-03", "items": []}),
    ("DELETE", "/api/v1/growth-records/{growth_id}", None),
    ("DELETE", "/api/v1/diet-records/{diet_id}", None),
    ("DELETE", "/api/v1/allergies/{allergy_id}", None),
    ("DELETE", "/api/v1/milestones/{milestone_id}", None),
    ("PATCH", "/api/v1/notifications/{notification_id}/read", None),
]


def _register_and_login(client, phone: str, nickname: str) -> dict:
    """幂等注册并登录指定手机号，返回鉴权请求头。

    @param client: 测试客户端
    @param phone: 手机号（已存在时跳过注册直接登录）
    @param nickname: 注册昵称
    @return: {"Authorization": "Bearer <token>"}
    @raises AssertionError: 注册/登录业务码异常时抛出
    """
    reg = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": SEC_PASSWORD, "nickname": nickname},
    )
    assert reg.json()["code"] in (0, 40900), reg.text
    login = client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": SEC_PASSWORD}
    )
    assert login.json()["code"] == 0, login.text
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


@pytest.fixture()
def owner_ctx(client):
    """属主用户 A 及其全部资源上下文（越权矩阵的目标资源）。

    每个用例独立重建，保证 DELETE 类越权用例不污染后续用例。

    @param client: 测试客户端
    @return: 资源字典，含 baby_id/growth_id/diet_id/allergy_id/milestone_id/
             notification_id/favorite_recipe_id
    @raises AssertionError: 任一属主资源创建失败时抛出
    """
    headers = _register_and_login(client, PHONE_OWNER, "越权属主")
    baby = client.post(
        "/api/v1/babies",
        headers=headers,
        json={"name": "属主宝宝", "gender": "male", "birth_date": "2026-02-01"},
    ).json()["data"]
    baby_id = baby["id"]

    growth = client.post(
        f"/api/v1/babies/{baby_id}/growth-records",
        headers=headers,
        json={"record_date": "2026-09-01", "weight_kg": 8.0},
    ).json()["data"]
    diet = client.post(
        f"/api/v1/babies/{baby_id}/diet-records",
        headers=headers,
        json={
            "record_date": "2026-09-01",
            "record_type": "formula",
            "details": {"amount_ml": 120},
        },
    ).json()["data"]
    allergy = client.post(
        f"/api/v1/babies/{baby_id}/allergies", headers=headers, json={"ingredient": "芒果"}
    ).json()["data"]
    milestone = client.post(
        f"/api/v1/babies/{baby_id}/milestones",
        headers=headers,
        json={"milestone_type": "crawl", "name": "爬行", "achieved_at": "2026-09-01"},
    ).json()["data"]
    plan = client.put(
        f"/api/v1/babies/{baby_id}/meal-plans",
        headers=headers,
        json={
            "week_start": "2026-08-03",
            "items": [{"day_of_week": 0, "meal_type": "lunch", "recipe_id": 1}],
        },
    ).json()["data"]
    assert plan, "属主一周计划创建失败"

    favorite_recipe_id = 3
    fav_resp = client.post(
        f"/api/v1/recipes/{favorite_recipe_id}/favorite", headers=headers
    )
    assert fav_resp.json()["code"] == 0, fav_resp.text

    # 通知无创建接口，直接落库（与 test_notifications 的做法一致）
    from app.core.database import SessionLocal
    from app.models.notification import Notification

    me = client.get("/api/v1/users/me", headers=headers).json()["data"]
    with SessionLocal() as db:
        db.add(
            Notification(user_id=me["id"], notify_type="system", title="属主通知", content="仅属主可见")
        )
        db.commit()
    notifications = client.get("/api/v1/notifications", headers=headers).json()["data"]["items"]
    # 属主账号跨用例复用，历史通知会累积；列表按创建时间倒序，
    # 取同标题首条即为本用例最新插入的通知
    owner_notifications = [n for n in notifications if n["title"] == "属主通知"]
    assert owner_notifications, "属主通知创建失败"

    return {
        "headers": headers,
        "baby_id": baby_id,
        "growth_id": growth["id"],
        "diet_id": diet["id"],
        "allergy_id": allergy["id"],
        "milestone_id": milestone["id"],
        "notification_id": owner_notifications[0]["id"],
        "favorite_recipe_id": favorite_recipe_id,
    }


class TestCrossUserAccess:
    """跨用户越权矩阵测试组：用户 B 访问用户 A 的资源必须被拒绝。"""

    @pytest.mark.parametrize("method,path_template,payload", CROSS_ACCESS_CASES)
    def test_attacker_access_denied(self, client, owner_ctx, method, path_template, payload):
        """访客 B 对属主 A 各类资源的访问应统一返回 40400（含 B 向 A 宝宝写入数据的场景）。

        @param client: 测试客户端
        @param owner_ctx: 属主资源上下文夹具
        @param method: HTTP 方法
        @param path_template: 含占位符的路径模板
        @param payload: 请求体（可为 None）
        @raises AssertionError: 响应码或业务码不符合 40400 契约时抛出
        """
        attacker = _register_and_login(client, PHONE_ATTACKER, "越权访客")
        url = path_template.format(
            baby_id=owner_ctx["baby_id"],
            growth_id=owner_ctx["growth_id"],
            diet_id=owner_ctx["diet_id"],
            allergy_id=owner_ctx["allergy_id"],
            milestone_id=owner_ctx["milestone_id"],
            notification_id=owner_ctx["notification_id"],
        )
        resp = client.request(method, url, headers=attacker, json=payload)
        body = resp.json()
        assert resp.status_code == 200, f"{method} {url} HTTP={resp.status_code}"
        assert body["code"] == 40400, f"{method} {url} -> {body}"

    def test_attacker_list_views_do_not_contain_owner_data(self, client, owner_ctx):
        """访客 B 的列表接口（宝宝/收藏/通知）不应包含属主 A 的任何数据。

        @param client: 测试客户端
        @param owner_ctx: 属主资源上下文夹具
        @raises AssertionError: 列表中出现属主资源 ID 时抛出
        """
        attacker = _register_and_login(client, PHONE_ATTACKER, "越权访客")

        babies = client.get("/api/v1/babies", headers=attacker).json()["data"]
        assert all(b["id"] != owner_ctx["baby_id"] for b in babies)

        favorites = client.get("/api/v1/recipes/favorites", headers=attacker).json()["data"]
        assert all(f["recipe_id"] != owner_ctx["favorite_recipe_id"] for f in favorites)

        notifications = client.get(
            "/api/v1/notifications", headers=attacker
        ).json()["data"]["items"]
        assert all(n["id"] != owner_ctx["notification_id"] for n in notifications)


class TestSensitiveInfoLeak:
    """敏感信息泄露测试组：任何响应不得出现 password_hash 字段或异常细节。"""

    @staticmethod
    def _resp_text(resp) -> str:
        """将响应 JSON 完整序列化为小写文本，用于敏感词全文扫描。

        @param resp: 测试响应对象
        @return: 响应全文的小写字符串
        """
        return json.dumps(resp.json(), ensure_ascii=False).lower()

    def test_register_response_has_no_password_hash(self, client):
        """注册成功响应不得包含 password_hash 字段。

        @param client: 测试客户端
        @raises AssertionError: 响应中出现 password_hash 时抛出
        """
        resp = client.post(
            "/api/v1/auth/register",
            json={"phone": PHONE_LEAK_A, "password": "abc123456", "nickname": "泄露检测"},
        )
        assert resp.json()["code"] == 0
        assert "password_hash" not in self._resp_text(resp)

    def test_login_response_has_no_password_hash(self, client):
        """登录成功响应不得包含 password_hash 字段。

        @param client: 测试客户端
        @raises AssertionError: 响应中出现 password_hash 时抛出
        """
        client.post(
            "/api/v1/auth/register",
            json={"phone": PHONE_LEAK_B, "password": SEC_PASSWORD, "nickname": "泄露检测二"},
        )
        resp = client.post(
            "/api/v1/auth/login", json={"phone": PHONE_LEAK_B, "password": SEC_PASSWORD}
        )
        assert resp.json()["code"] == 0
        assert "password_hash" not in self._resp_text(resp)

    def test_error_responses_have_no_password_hash(self, client):
        """未认证/无效令牌/校验失败等错误响应不得包含 password_hash 字段。

        @param client: 测试客户端
        @raises AssertionError: 任一错误响应中出现 password_hash 时抛出
        """
        cases = [
            client.get("/api/v1/babies"),  # 未认证 40100
            client.get(  # 无效令牌 40100
                "/api/v1/babies", headers={"Authorization": "Bearer bad.token"}
            ),
            client.post("/api/v1/auth/register", json={"password": "abc123456"}),  # 42200
        ]
        for resp in cases:
            assert resp.json()["code"] != 0
            assert "password_hash" not in self._resp_text(resp), resp.text

    def test_500_returns_unified_message_without_details(
        self, client, auth_headers, monkeypatch
    ):
        """未捕获异常应兜底为 HTTP 500 + 50000：message 为统一文案，不含异常细节与堆栈。

        通过 monkeypatch 令宝宝详情端点抛出携带敏感串的 RuntimeError，
        验证兜底处理器不回显任何异常信息。

        @param client: 测试客户端（用于 auth_headers 夹具链）
        @param auth_headers: 鉴权请求头夹具
        @param monkeypatch: pytest monkeypatch 夹具
        @raises AssertionError: 500 响应泄露异常细节时抛出
        """
        import app.api.v1.babies as babies_module

        def _boom(*_args, **_kwargs):
            """模拟端点内部未捕获异常，消息中埋入凭据串与堆栈特征。

            @param _args: 位置参数（忽略）
            @param _kwargs: 关键字参数（忽略）
            @raises RuntimeError: 携带敏感信息的模拟异常
            """
            raise RuntimeError(
                "db connect failed: mysql://root:520118@127.0.0.1/db "
                'Traceback (most recent call last) File "app/models/user.py"'
            )

        monkeypatch.setattr(babies_module, "get_baby_or_404", _boom)

        # raise_server_exceptions=False 使 500 响应直达断言而非向上抛出
        with TestClient(app, raise_server_exceptions=False) as tolerant:
            resp = tolerant.get("/api/v1/babies/1/summary", headers=auth_headers)

        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == 50000
        assert body["message"] == "服务器内部错误，请稍后重试"
        assert body["data"] is None
        text = self._resp_text(resp)
        for leak in ("520118", "root:", "runtimeerror", "traceback", ".py", "app/"):
            assert leak not in text, f"500 响应泄露敏感串 {leak}: {text}"


class TestCorsWhitelist:
    """CORS 白名单测试组：中间件配置必须来源于 settings.cors_origin_list。"""

    def test_middleware_origins_from_settings(self):
        """应用应注册唯一 CORSMiddleware，且 allow_origins 与配置白名单一致。

        @raises AssertionError: 中间件缺失/重复或配置不一致时抛出
        """
        cors_entries = [mw for mw in app.user_middleware if mw.cls is CORSMiddleware]
        assert len(cors_entries) == 1, "应只注册一个 CORSMiddleware"
        entry = cors_entries[0]
        assert entry.kwargs["allow_origins"] == settings.cors_origin_list
        assert entry.kwargs["allow_credentials"] is True

    def test_preflight_allowed_origin(self, client):
        """白名单来源的预检请求应放行并回显 access-control-allow-origin。

        @param client: 测试客户端
        @raises AssertionError: 预检未放行或未回显来源时抛出
        """
        origin = settings.cors_origin_list[0]
        resp = client.options(
            "/api/v1/recipes",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == origin

    def test_preflight_rejects_unknown_origin(self, client):
        """非白名单来源的预检请求不应获得 access-control-allow-origin 放行头。

        @param client: 测试客户端
        @raises AssertionError: 非白名单来源被放行时抛出
        """
        resp = client.options(
            "/api/v1/recipes",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") is None


class TestRateLimitThreadSafety:
    """限流器并发安全测试组（test_login_rate_limit.py 未覆盖的并发维度）。"""

    def test_concurrent_record_failure_counts_exactly(self):
        """多线程并发 record_failure 同一手机号时失败计数不得丢失。

        并发注入 workers*per_thread 次失败（阈值 +1 不触发锁定），随后补记
        1 次应恰好达到阈值并锁定：若并发导致计数丢失，补记后将达不到阈值，
        锁定断言失败，以此黑盒验证计数精确性。

        @raises AssertionError: 计数丢失或提前/滞后锁定时抛出
        """
        phone = "13833336666"
        workers, per_thread = 20, 10
        threshold = workers * per_thread + 1

        def worker():
            """单线程工作体：连续记录 per_thread 次失败。

            @return: 无返回值，副作用为累加该手机号的失败计数
            """
            for _ in range(per_thread):
                rate_limit.record_failure(phone, max_failures=threshold, lock_minutes=15)

        threads = [threading.Thread(target=worker) for _ in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 200 次失败 < 201 阈值：不应锁定
        assert rate_limit.is_locked(phone) is False
        # 补记 1 次恰好达阈值：并发计数无丢失则应立即锁定
        rate_limit.record_failure(phone, max_failures=threshold)
        assert rate_limit.is_locked(phone) is True
        rate_limit.clear(phone)

    def test_concurrent_distinct_phones_isolated(self):
        """多手机号并发失败计数互不干扰，各自达到阈值后独立锁定。

        @raises AssertionError: 任一手机号未按自身计数锁定时抛出
        """
        phones = [f"1384444{i:04d}" for i in range(10)]

        def worker(p: str):
            """单线程工作体：对指定手机号记录恰好 2 次失败。

            @param p: 目标手机号
            @return: 无返回值，副作用为该手机号失败计数达到 2
            """
            rate_limit.record_failure(p, max_failures=2)
            rate_limit.record_failure(p, max_failures=2)

        threads = [threading.Thread(target=worker, args=(p,)) for p in phones]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for p in phones:
            assert rate_limit.is_locked(p) is True
        rate_limit.reset()
