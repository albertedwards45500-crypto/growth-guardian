"""
@file: tests/test_recipes.py
@description: 辅食推荐模块集成测试：筛选、收藏、智能推荐与一周计划。
"""

from datetime import date

from app.services.growth import compute_age
from tests.conftest import create_test_baby


class TestRecipeList:
    """食谱筛选测试组。"""

    def test_list_recipes_paged(self, client, auth_headers):
        """食谱列表应分页返回。"""
        resp = client.get("/api/v1/recipes", headers=auth_headers, params={"page": 1, "page_size": 5})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 20
        assert len(data["items"]) == 5
        assert "is_favorite" in data["items"][0]

    def test_filter_by_age(self, client, auth_headers):
        """按月龄筛选：6 个月应只返回适合 6 个月的食谱。"""
        resp = client.get("/api/v1/recipes", headers=auth_headers, params={"age_months": 6})
        for item in resp.json()["data"]["items"]:
            assert item["suitable_age_min"] <= 6 <= item["suitable_age_max"]

    def test_filter_by_keyword(self, client, auth_headers):
        """按关键词搜索食谱。"""
        resp = client.get("/api/v1/recipes", headers=auth_headers, params={"keyword": "南瓜"})
        for item in resp.json()["data"]["items"]:
            assert "南瓜" in item["title"]

    def test_filter_by_nutrition(self, client, auth_headers):
        """按营养标签筛选食谱。"""
        resp = client.get("/api/v1/recipes", headers=auth_headers, params={"nutrition": "补铁"})
        items = resp.json()["data"]["items"]
        assert len(items) > 0
        for item in items:
            assert any("铁" in tag for tag in item["nutrition_tags"])

    def test_recipe_detail(self, client, auth_headers):
        """食谱详情应包含步骤与食材清单。"""
        resp = client.get("/api/v1/recipes/1", headers=auth_headers)
        data = resp.json()["data"]
        assert data["steps"]
        assert data["ingredients"]

    def test_recipe_not_found(self, client, auth_headers):
        """不存在的食谱应返回 404。"""
        resp = client.get("/api/v1/recipes/99999", headers=auth_headers)
        assert resp.json()["code"] == 40400


class TestFavorite:
    """食谱收藏测试组。"""

    def test_favorite_flow(self, client, auth_headers):
        """收藏、查询、取消收藏全流程。"""
        resp = client.post("/api/v1/recipes/1/favorite", headers=auth_headers)
        assert resp.json()["data"]["favorited"] is True

        favorites = client.get("/api/v1/recipes/favorites", headers=auth_headers).json()["data"]
        assert any(f["recipe_id"] == 1 for f in favorites)

        # 详情中应标记已收藏
        detail = client.get("/api/v1/recipes/1", headers=auth_headers).json()["data"]
        assert detail["is_favorite"] is True

        resp = client.delete("/api/v1/recipes/1/favorite", headers=auth_headers)
        assert resp.json()["data"]["favorited"] is False

    def test_favorite_idempotent(self, client, auth_headers):
        """重复收藏应幂等成功。"""
        client.post("/api/v1/recipes/2/favorite", headers=auth_headers)
        resp = client.post("/api/v1/recipes/2/favorite", headers=auth_headers)
        assert resp.json()["data"]["favorited"] is True
        favorites = client.get("/api/v1/recipes/favorites", headers=auth_headers).json()["data"]
        assert len([f for f in favorites if f["recipe_id"] == 2]) == 1


class TestRecommendation:
    """智能推荐测试组。"""

    def test_recommend_with_allergen_exclusion(self, client, auth_headers):
        """过敏食材应被自动规避（如添加"南瓜"过敏后不再推荐南瓜食谱）。"""
        baby = create_test_baby(client, auth_headers)
        # 记录南瓜过敏
        client.post(
            f"/api/v1/babies/{baby['id']}/allergies",
            headers=auth_headers,
            json={"ingredient": "南瓜"},
        )
        resp = client.get(
            f"/api/v1/babies/{baby['id']}/recipes/recommendations", headers=auth_headers
        )
        assert resp.status_code == 200
        # D09 分页契约：推荐结果包装为 {items, total, page, page_size}
        for item in resp.json()["data"]["items"]:
            names = [ing.get("name", "") for ing in item["ingredients"]]
            assert not any("南瓜" in n for n in names)

    def test_recommend_age_matched(self, client, demo_headers):
        """推荐食谱应适配演示宝宝月龄（8 个月爬行期场景）。

        期望值动态推导（修复 D01 测试硬编码问题）：演示宝宝出生日期由种子
        逻辑相对当前日期生成，此处从接口返回的 birth_date 用 compute_age
        推导期望月龄，断言每条推荐满足 suitable_age_min <= 月龄 <=
        suitable_age_max，而非硬编码月龄 8。

        @param client: 测试 HTTP 客户端夹具
        @param demo_headers: 演示账号鉴权头夹具
        @return: 无返回值，断言失败时抛出 AssertionError
        """
        babies = client.get("/api/v1/babies", headers=demo_headers).json()["data"]
        demo_baby = babies[0]
        baby_id = demo_baby["id"]
        # 期望月龄由演示宝宝真实出生日期动态推导
        age_months, _ = compute_age(date.fromisoformat(demo_baby["birth_date"]))
        assert age_months == 8  # 种子设计保证演示宝宝恒为 8 个月大

        resp = client.get(
            f"/api/v1/babies/{baby_id}/recipes/recommendations", headers=demo_headers
        )
        assert resp.status_code == 200
        # 推荐接口已统一为分页结构 {items, total, page, page_size}
        data = resp.json()["data"]
        assert data["total"] >= 1  # 8 月龄演示宝宝应至少有 1 条适配推荐
        for item in data["items"]:
            assert item["suitable_age_min"] <= age_months <= item["suitable_age_max"]


class TestMealPlan:
    """一周辅食计划测试组。"""

    def test_upsert_and_get_meal_plans(self, client, auth_headers):
        """保存并查询一周辅食计划。"""
        baby = create_test_baby(client, auth_headers)
        payload = {
            "week_start": "2026-08-03",
            "items": [
                {"day_of_week": 0, "meal_type": "lunch", "recipe_id": 1},
                {"day_of_week": 1, "meal_type": "dinner", "recipe_id": 2, "note": "晚餐"},
            ],
        }
        resp = client.put(
            f"/api/v1/babies/{baby['id']}/meal-plans", headers=auth_headers, json=payload
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) == 2
        assert items[0]["recipe_title"]

        # 覆盖写入同一周应替换旧数据
        resp = client.put(
            f"/api/v1/babies/{baby['id']}/meal-plans",
            headers=auth_headers,
            json={"week_start": "2026-08-03", "items": []},
        )
        assert len(resp.json()["data"]) == 0


class TestRecommendPagination:
    """推荐接口分页与过敏下推过滤测试组（D09/D10）。"""

    def test_recommend_paged(self, client, auth_headers):
        """推荐接口应支持 page/page_size 并返回 total（D09 分页契约）。"""
        baby = create_test_baby(client, auth_headers)
        url = f"/api/v1/babies/{baby['id']}/recipes/recommendations"
        resp = client.get(url, headers=auth_headers, params={"page": 1, "page_size": 3})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] > 3
        assert data["page"] == 1
        assert data["page_size"] == 3
        assert len(data["items"]) == 3

        # 翻页结果不重叠
        resp2 = client.get(url, headers=auth_headers, params={"page": 2, "page_size": 3})
        ids_page1 = {item["id"] for item in data["items"]}
        ids_page2 = {item["id"] for item in resp2.json()["data"]["items"]}
        assert ids_page1.isdisjoint(ids_page2)

    def test_recommend_invalid_page_returns_42200(self, client, auth_headers):
        """非法分页参数（page=0）应由统一校验契约返回 42200。"""
        baby = create_test_baby(client, auth_headers)
        resp = client.get(
            f"/api/v1/babies/{baby['id']}/recipes/recommendations",
            headers=auth_headers,
            params={"page": 0},
        )
        assert resp.json()["code"] == 42200

    def test_recommend_excludes_allergen_recipes(self, client, auth_headers):
        """添加过敏食材后推荐应排除含该食材的食谱（D10 SQL 下推过滤）。"""
        baby = create_test_baby(client, auth_headers)
        url = f"/api/v1/babies/{baby['id']}/recipes/recommendations"

        # 过敏前：当前月龄推荐中存在含蛋黄的食谱（种子数据"蛋黄米粥"）
        before = client.get(url, headers=auth_headers).json()["data"]
        assert any(
            "蛋黄" in ing.get("name", "")
            for item in before["items"]
            for ing in item["ingredients"]
        )

        # 记录蛋黄过敏后：推荐结果不再包含蛋黄食材
        resp = client.post(
            f"/api/v1/babies/{baby['id']}/allergies",
            headers=auth_headers,
            json={"ingredient": "蛋黄"},
        )
        assert resp.status_code == 200, resp.text

        after = client.get(url, headers=auth_headers).json()["data"]
        assert after["total"] < before["total"]
        for item in after["items"]:
            names = [ing.get("name", "") for ing in item["ingredients"]]
            assert not any("蛋黄" in n for n in names)

    def test_recommend_age_boundary_dynamic(self, client, auth_headers):
        """月龄边界动态断言：推荐结果应全部覆盖宝宝实际月龄。

        期望月龄由宝宝出生日期经 compute_age 动态推导，不硬编码，
        保证测试不随系统日期推移而失效。

        @param client: 测试 HTTP 客户端夹具
        @param auth_headers: 鉴权请求头夹具
        @return: 无返回值，断言失败时抛出 AssertionError
        """
        baby = create_test_baby(client, auth_headers)
        age_months, _ = compute_age(date.fromisoformat(baby["birth_date"]))
        resp = client.get(
            f"/api/v1/babies/{baby['id']}/recipes/recommendations", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] > 0
        for item in data["items"]:
            assert item["suitable_age_min"] <= age_months <= item["suitable_age_max"]
