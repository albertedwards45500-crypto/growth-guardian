"""
@file: tests/test_diet.py
@description: 饮食管理模块集成测试：三类饮食记录、营养分析与过敏管理。
"""

from tests.conftest import create_test_baby


class TestDietRecord:
    """饮食记录测试组。"""

    def _post(self, client, headers, baby_id, payload):
        """新增饮食记录公共方法。

        @param client: 测试客户端
        @param headers: 鉴权头
        @param baby_id: 宝宝 ID
        @param payload: 请求体
        @return: 响应 JSON
        """
        return client.post(
            f"/api/v1/babies/{baby_id}/diet-records", headers=headers, json=payload
        )

    def test_breast_milk_record(self, client, auth_headers):
        """母乳喂养记录应保存左右侧时长。"""
        baby = create_test_baby(client, auth_headers)
        resp = self._post(
            client,
            auth_headers,
            baby["id"],
            {
                "record_date": "2026-08-01",
                "record_type": "breast_milk",
                "details": {"left_minutes": 15, "right_minutes": 10},
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["details"]["left_minutes"] == 15
        assert data["details"]["right_minutes"] == 10

    def test_formula_record(self, client, auth_headers):
        """配方奶记录应保存奶量。"""
        baby = create_test_baby(client, auth_headers)
        resp = self._post(
            client,
            auth_headers,
            baby["id"],
            {
                "record_date": "2026-08-01",
                "record_type": "formula",
                "details": {"amount_ml": 120},
            },
        )
        assert resp.json()["data"]["details"]["amount_ml"] == 120

    def test_solid_food_record(self, client, auth_headers):
        """辅食记录应保存食材与反应备注。"""
        baby = create_test_baby(client, auth_headers)
        resp = self._post(
            client,
            auth_headers,
            baby["id"],
            {
                "record_date": "2026-08-01",
                "record_type": "solid_food",
                "details": {"food_items": ["南瓜泥", "苹果泥"]},
                "note": "第一次尝试南瓜泥，没有排斥反应",
            },
        )
        data = resp.json()["data"]
        assert "南瓜泥" in data["details"]["food_items"]
        assert "没有排斥反应" in data["note"]

    def test_breast_milk_without_details(self, client, auth_headers):
        """母乳记录缺少时长明细应返回业务错误。"""
        baby = create_test_baby(client, auth_headers)
        resp = self._post(
            client,
            auth_headers,
            baby["id"],
            {"record_date": "2026-08-01", "record_type": "breast_milk", "details": {}},
        )
        assert resp.json()["code"] == 40002

    def test_list_by_date(self, client, auth_headers):
        """按日期过滤饮食记录（D09 分页契约：响应含 items 与 total）。"""
        baby = create_test_baby(client, auth_headers)
        self._post(
            client,
            auth_headers,
            baby["id"],
            {
                "record_date": "2026-08-01",
                "record_type": "formula",
                "details": {"amount_ml": 100},
            },
        )
        resp = client.get(
            f"/api/v1/babies/{baby['id']}/diet-records",
            headers=auth_headers,
            params={"record_date": "2026-08-01"},
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["record_type"] == "formula"


class TestDietAnalysis:
    """营养分析测试组。"""

    def test_nutrition_summary(self, client, auth_headers):
        """营养分析应正确聚合当日三类记录。"""
        baby = create_test_baby(client, auth_headers)
        # 母乳 15+10 分钟
        client.post(
            f"/api/v1/babies/{baby['id']}/diet-records",
            headers=auth_headers,
            json={
                "record_date": "2026-08-01",
                "record_type": "breast_milk",
                "details": {"left_minutes": 15, "right_minutes": 10},
            },
        )
        # 配方奶 120ml
        client.post(
            f"/api/v1/babies/{baby['id']}/diet-records",
            headers=auth_headers,
            json={
                "record_date": "2026-08-01",
                "record_type": "formula",
                "details": {"amount_ml": 120},
            },
        )
        # 辅食两次
        client.post(
            f"/api/v1/babies/{baby['id']}/diet-records",
            headers=auth_headers,
            json={
                "record_date": "2026-08-01",
                "record_type": "solid_food",
                "details": {"food_items": ["南瓜泥"]},
            },
        )
        resp = client.get(
            f"/api/v1/babies/{baby['id']}/diet-analysis",
            headers=auth_headers,
            params={"target_date": "2026-08-01"},
        )
        data = resp.json()["data"]
        assert data["feed_count"] == 3
        assert data["breast_milk_minutes"] == 25
        assert data["formula_amount_ml"] == 120
        assert data["solid_food_count"] == 1
        assert "南瓜泥" in data["food_names"]


class TestAllergy:
    """过敏食材管理测试组。"""

    def test_allergy_crud(self, client, auth_headers):
        """过敏食材增删查。"""
        baby = create_test_baby(client, auth_headers)
        resp = client.post(
            f"/api/v1/babies/{baby['id']}/allergies",
            headers=auth_headers,
            json={"ingredient": "鸡蛋", "severity": "moderate"},
        )
        assert resp.status_code == 200

        # 重复添加应冲突
        dup = client.post(
            f"/api/v1/babies/{baby['id']}/allergies",
            headers=auth_headers,
            json={"ingredient": "鸡蛋"},
        )
        assert dup.json()["code"] == 40900

        resp = client.get(f"/api/v1/babies/{baby['id']}/allergies", headers=auth_headers)
        ingredients = [a["ingredient"] for a in resp.json()["data"]]
        assert "鸡蛋" in ingredients

        allergy_id = resp.json()["data"][0]["id"]
        resp = client.delete(f"/api/v1/allergies/{allergy_id}", headers=auth_headers)
        assert resp.json()["data"]["deleted"] is True
