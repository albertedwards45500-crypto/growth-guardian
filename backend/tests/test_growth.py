"""
@file: tests/test_growth.py
@description: 成长记录模块集成测试：生长记录、生长曲线与里程碑。
"""

from tests.conftest import create_test_baby


class TestGrowthRecord:
    """生长记录测试组。"""

    def _create(self, client, headers, baby_id, **overrides):
        """创建生长记录的公共方法。

        @param client: 测试客户端
        @param headers: 鉴权头
        @param baby_id: 宝宝 ID
        @return: 创建响应 JSON
        """
        payload = {
            "record_date": "2026-08-01",
            "weight_kg": 8.5,
            "height_cm": 72,
            "head_circumference_cm": 44,
        }
        payload.update(overrides)
        return client.post(
            f"/api/v1/babies/{baby_id}/growth-records", headers=headers, json=payload
        )

    def test_create_growth_record(self, client, auth_headers):
        """新增生长记录应成功。"""
        baby = create_test_baby(client, auth_headers)
        resp = self._create(client, auth_headers, baby["id"])
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["weight_kg"] == 8.5
        assert data["height_cm"] == 72

    def test_create_record_all_fields_empty(self, client, auth_headers):
        """三项指标全空应返回业务错误。"""
        baby = create_test_baby(client, auth_headers)
        resp = self._create(client, auth_headers, baby["id"], weight_kg=None, height_cm=None, head_circumference_cm=None)
        assert resp.json()["code"] == 40001

    def test_create_record_future_date(self, client, auth_headers):
        """未来日期应返回参数校验错误。"""
        baby = create_test_baby(client, auth_headers)
        resp = self._create(client, auth_headers, baby["id"], record_date="2030-01-01")
        assert resp.json()["code"] == 42200

    def test_list_and_delete_growth_records(self, client, auth_headers):
        """生长记录列表与删除应正常。"""
        baby = create_test_baby(client, auth_headers)
        rec = self._create(client, auth_headers, baby["id"]).json()["data"]
        resp = client.get(f"/api/v1/babies/{baby['id']}/growth-records", headers=auth_headers)
        assert len(resp.json()["data"]) >= 1

        del_resp = client.delete(f"/api/v1/growth-records/{rec['id']}", headers=auth_headers)
        assert del_resp.json()["data"]["deleted"] is True

    def test_growth_curve(self, client, auth_headers):
        """生长曲线应按维度返回数据点（含月龄坐标）。"""
        baby = create_test_baby(client, auth_headers)
        self._create(client, auth_headers, baby["id"])
        resp = client.get(f"/api/v1/babies/{baby['id']}/growth-curve", headers=auth_headers)
        curve = resp.json()["data"]
        assert len(curve["weight_series"]) == 1
        point = curve["weight_series"][0]
        assert point["age_months"] >= 0
        assert point["weight_kg"] == 8.5


class TestMilestone:
    """里程碑测试组。"""

    def test_create_and_list_milestones(self, client, auth_headers):
        """新增并查询里程碑。"""
        baby = create_test_baby(client, auth_headers)
        resp = client.post(
            f"/api/v1/babies/{baby['id']}/milestones",
            headers=auth_headers,
            json={"milestone_type": "crawl", "name": "爬行", "achieved_at": "2026-08-01"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "爬行"

        resp = client.get(f"/api/v1/babies/{baby['id']}/milestones", headers=auth_headers)
        types = [m["milestone_type"] for m in resp.json()["data"]]
        assert "crawl" in types

    def test_delete_milestone(self, client, auth_headers):
        """删除里程碑。"""
        baby = create_test_baby(client, auth_headers)
        ms = client.post(
            f"/api/v1/babies/{baby['id']}/milestones",
            headers=auth_headers,
            json={"milestone_type": "walk", "name": "行走", "achieved_at": "2026-08-01"},
        ).json()["data"]
        resp = client.delete(f"/api/v1/milestones/{ms['id']}", headers=auth_headers)
        assert resp.json()["data"]["deleted"] is True
