"""
@file: tests/test_e2e_flow.py
@description: 系统链路端到端测试：以随机新用户串联"注册 → 登录 → 建档 → 成长记录 →
             生长曲线（含 WHO 参考）→ 里程碑 → 辅食记录 → 营养分析 → 过敏规避推荐 →
             一周计划 → 食谱浏览/收藏 → 喂养指南/FAQ → 通知"完整业务链路，
             收尾断言多用户数据隔离。
"""

import random
from datetime import date, timedelta

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.notification import Notification
from app.services.growth import compute_age

E2E_PASSWORD = "e2e123456"


def _random_phone() -> str:
    """生成随机测试手机号（139 + 8 位随机数字），与其他测试/演示数据天然隔离。

    @return: 11 位手机号字符串
    """
    return "139" + str(random.randint(10_000_000, 99_999_999))


def _register_and_login(client, phone: str, nickname: str) -> dict:
    """注册并登录新用户，返回鉴权请求头。

    @param client: 测试客户端
    @param phone: 手机号（随机生成，无需幂等处理）
    @param nickname: 注册昵称
    @return: {"Authorization": "Bearer <token>"}
    @raises AssertionError: 注册或登录业务码非 0 时抛出
    """
    reg = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "password": E2E_PASSWORD, "nickname": nickname},
    )
    assert reg.json()["code"] == 0, reg.text
    login = client.post(
        "/api/v1/auth/login", json={"phone": phone, "password": E2E_PASSWORD}
    )
    assert login.json()["code"] == 0, login.text
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


class TestFullUserJourney:
    """系统链路端到端测试组：单个用例串联核心业务全流程。"""

    def test_full_user_journey(self, client):
        """新用户从注册到通知的完整业务链路，收尾断言多用户数据隔离。

        @param client: 测试客户端
        @raises AssertionError: 链路任一步骤业务码非 0 或关键字段不符时抛出
        """
        today = date.today()
        # 出生日期约 8 个月前：保证推荐/指南命中"6-8 个月爬行期"数据段
        birth = today - timedelta(days=245)

        # ---- 步骤 1：注册新用户（随机手机号）----
        phone = _random_phone()
        reg = client.post(
            "/api/v1/auth/register",
            json={"phone": phone, "password": E2E_PASSWORD, "nickname": "链路用户"},
        )
        assert reg.status_code == 200
        reg_body = reg.json()
        assert reg_body["code"] == 0, reg_body
        assert reg_body["data"]["phone"] == phone
        assert "password_hash" not in reg_body["data"]

        # ---- 步骤 2：登录拿 token（有效期应来自配置）----
        login = client.post(
            "/api/v1/auth/login", json={"phone": phone, "password": E2E_PASSWORD}
        )
        assert login.json()["code"] == 0
        token_data = login.json()["data"]
        assert token_data["access_token"]
        assert token_data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}

        # ---- 步骤 3：创建宝宝 ----
        baby = client.post(
            "/api/v1/babies",
            headers=headers,
            json={"name": "链路宝宝", "gender": "female", "birth_date": birth.isoformat()},
        ).json()["data"]
        baby_id = baby["id"]
        assert baby["name"] == "链路宝宝"
        assert baby["is_default"] is True

        age_months, _ = compute_age(birth, today)

        # ---- 步骤 4：添加成长记录（身高/体重/头围）----
        rec = client.post(
            f"/api/v1/babies/{baby_id}/growth-records",
            headers=headers,
            json={
                "record_date": today.isoformat(),
                "weight_kg": 8.5,
                "height_cm": 72.0,
                "head_circumference_cm": 44.0,
            },
        )
        assert rec.json()["code"] == 0, rec.text
        rec_data = rec.json()["data"]
        assert rec_data["weight_kg"] == 8.5
        assert rec_data["height_cm"] == 72.0
        assert rec_data["head_circumference_cm"] == 44.0

        # ---- 步骤 5：查询成长曲线（含 who_reference）----
        curve = client.get(
            f"/api/v1/babies/{baby_id}/growth-curve", headers=headers
        ).json()["data"]
        assert len(curve["weight_series"]) == 1
        assert curve["weight_series"][0]["age_months"] == age_months
        assert curve["weight_series"][0]["weight_kg"] == 8.5
        who = curve["who_reference"]
        assert who is not None, "24 月龄内宝宝应返回 WHO 参考线"
        assert who["height"] and who["weight"]
        assert max(p["month"] for p in who["height"]) >= age_months
        assert all(p["p50"] > 0 for p in who["height"])

        # ---- 步骤 6：添加里程碑 ----
        ms = client.post(
            f"/api/v1/babies/{baby_id}/milestones",
            headers=headers,
            json={"milestone_type": "crawl", "name": "爬行", "achieved_at": today.isoformat()},
        ).json()["data"]
        assert ms["name"] == "爬行"
        assert ms["milestone_type"] == "crawl"

        # ---- 步骤 7：添加饮食记录（辅食）----
        diet = client.post(
            f"/api/v1/babies/{baby_id}/diet-records",
            headers=headers,
            json={
                "record_date": today.isoformat(),
                "record_type": "solid_food",
                "details": {"food_items": ["南瓜泥", "苹果泥"]},
                "note": "接受度良好",
            },
        ).json()["data"]
        assert diet["record_type"] == "solid_food"
        assert diet["details"]["food_items"] == ["南瓜泥", "苹果泥"]

        # ---- 步骤 8：查询营养分析 ----
        analysis = client.get(
            f"/api/v1/babies/{baby_id}/diet-analysis",
            headers=headers,
            params={"target_date": today.isoformat()},
        ).json()["data"]
        assert analysis["feed_count"] == 1
        assert analysis["solid_food_count"] == 1
        assert "南瓜泥" in analysis["food_names"]
        assert "苹果泥" in analysis["food_names"]

        # ---- 步骤 9：添加过敏食材并获取推荐（断言不含过敏食材）----
        add_allergy = client.post(
            f"/api/v1/babies/{baby_id}/allergies",
            headers=headers,
            json={"ingredient": "南瓜", "severity": "moderate"},
        )
        assert add_allergy.json()["code"] == 0, add_allergy.text
        allergies = client.get(
            f"/api/v1/babies/{baby_id}/allergies", headers=headers
        ).json()["data"]
        assert any(a["ingredient"] == "南瓜" for a in allergies)

        reco = client.get(
            f"/api/v1/babies/{baby_id}/recipes/recommendations", headers=headers
        ).json()["data"]
        assert reco["total"] > 0, "爬行期宝宝应有推荐结果"
        for item in reco["items"]:
            names = [ing["name"] for ing in item["ingredients"]]
            assert not any("南瓜" in n for n in names), f"推荐泄露过敏食材: {item['title']}"
            # SQL 下推过滤后月龄适配仍正确
            assert item["suitable_age_min"] <= age_months <= item["suitable_age_max"]

        # ---- 步骤 10：保存并查询一周计划 ----
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        saved = client.put(
            f"/api/v1/babies/{baby_id}/meal-plans",
            headers=headers,
            json={
                "week_start": week_start,
                "items": [{"day_of_week": 0, "meal_type": "lunch", "recipe_id": 1}],
            },
        )
        assert saved.json()["code"] == 0, saved.text
        plan_items = saved.json()["data"]
        assert len(plan_items) == 1
        assert plan_items[0]["day_of_week"] == 0
        assert plan_items[0]["recipe_id"] == 1
        assert plan_items[0]["recipe_title"]

        got_plan = client.get(
            f"/api/v1/babies/{baby_id}/meal-plans",
            headers=headers,
            params={"week_start": week_start},
        ).json()["data"]
        assert len(got_plan) == 1
        assert got_plan[0]["id"] == plan_items[0]["id"]

        # ---- 步骤 11：查询食谱列表并收藏一个食谱 ----
        recipes = client.get(
            "/api/v1/recipes", headers=headers, params={"page": 1, "page_size": 5}
        ).json()["data"]
        assert recipes["total"] > 0
        assert len(recipes["items"]) == 5
        target = recipes["items"][0]

        fav = client.post(f"/api/v1/recipes/{target['id']}/favorite", headers=headers)
        assert fav.json()["code"] == 0
        assert fav.json()["data"]["favorited"] is True

        favorites = client.get("/api/v1/recipes/favorites", headers=headers).json()["data"]
        assert any(f["recipe_id"] == target["id"] for f in favorites)
        detail = client.get(f"/api/v1/recipes/{target['id']}", headers=headers).json()["data"]
        assert detail["is_favorite"] is True

        # ---- 步骤 12：查询喂养指南（按月龄）与 FAQ（关键词）----
        guide = client.get(
            "/api/v1/advice/guides", headers=headers, params={"month": age_months}
        ).json()["data"]
        assert guide is not None
        assert guide["month_start"] <= age_months <= guide["month_end"]
        assert guide["title"]

        faqs = client.get(
            "/api/v1/advice/faqs", headers=headers, params={"keyword": "便秘"}
        ).json()["data"]
        assert len(faqs) >= 1, "关键词'便秘'应命中知识库"
        assert any("便秘" in f["question"] + f["answer"] for f in faqs)

        # ---- 步骤 13：通知列表/未读数/标记已读 ----
        me = client.get("/api/v1/users/me", headers=headers).json()["data"]
        with SessionLocal() as db:
            db.add(
                Notification(user_id=me["id"], notify_type="system", title="疫苗提醒", content="链路通知一")
            )
            db.add(
                Notification(user_id=me["id"], notify_type="system", title="体检提醒", content="链路通知二")
            )
            db.commit()

        notif_list = client.get("/api/v1/notifications", headers=headers).json()["data"]
        assert notif_list["total"] == 2
        unread = client.get(
            "/api/v1/notifications/unread-count", headers=headers
        ).json()["data"]
        assert unread["unread_count"] == 2

        nid = notif_list["items"][0]["id"]
        patched = client.patch(f"/api/v1/notifications/{nid}/read", headers=headers)
        assert patched.json()["code"] == 0
        assert patched.json()["data"]["is_read"] is True
        unread_after = client.get(
            "/api/v1/notifications/unread-count", headers=headers
        ).json()["data"]
        assert unread_after["unread_count"] == 1

        # ---- 步骤 14：用户隔离（新用户 B 只能看到自己的宝宝）----
        phone_b = _random_phone()
        headers_b = _register_and_login(client, phone_b, "隔离用户B")
        b_baby = client.post(
            "/api/v1/babies",
            headers=headers_b,
            json={"name": "B家宝宝", "gender": "male", "birth_date": birth.isoformat()},
        ).json()["data"]

        babies_b = client.get("/api/v1/babies", headers=headers_b).json()["data"]
        assert len(babies_b) == 1, "用户 B 的宝宝列表只应包含自己的宝宝"
        assert babies_b[0]["id"] == b_baby["id"]
        assert babies_b[0]["id"] != baby_id
