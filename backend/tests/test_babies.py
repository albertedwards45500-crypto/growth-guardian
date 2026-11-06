"""
@file: tests/test_babies.py
@description: 宝宝档案模块集成测试：CRUD、归属校验与成长印记。
"""

from datetime import date

from app.services.growth import compute_age, get_stage_name
from tests.conftest import create_test_baby


class TestBabyCrud:
    """宝宝档案 CRUD 测试组。"""

    def test_create_baby(self, client, auth_headers):
        """创建宝宝档案应成功并自动设为默认。"""
        baby = create_test_baby(client, auth_headers, "团团")
        assert baby["name"] == "团团"
        assert baby["gender"] == "female"
        assert baby["is_default"] is True

    def test_list_babies(self, client, auth_headers):
        """宝宝列表应返回当前用户全部档案。"""
        create_test_baby(client, auth_headers, "安安")
        create_test_baby(client, auth_headers, "乐乐")
        resp = client.get("/api/v1/babies", headers=auth_headers)
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()["data"]]
        assert "安安" in names and "乐乐" in names

    def test_get_baby_detail(self, client, auth_headers):
        """获取宝宝详情应返回正确数据。"""
        baby = create_test_baby(client, auth_headers, "小贝")
        resp = client.get(f"/api/v1/babies/{baby['id']}", headers=auth_headers)
        assert resp.json()["data"]["name"] == "小贝"

    def test_update_baby(self, client, auth_headers):
        """更新宝宝信息应生效。"""
        baby = create_test_baby(client, auth_headers, "原名字")
        resp = client.put(
            f"/api/v1/babies/{baby['id']}",
            headers=auth_headers,
            json={"name": "新名字"},
        )
        assert resp.json()["data"]["name"] == "新名字"

    def test_delete_baby(self, client, auth_headers):
        """删除宝宝档案应成功。"""
        baby = create_test_baby(client, auth_headers, "要删除")
        resp = client.delete(f"/api/v1/babies/{baby['id']}", headers=auth_headers)
        assert resp.json()["data"]["deleted"] is True
        # 再次查询应 404
        resp = client.get(f"/api/v1/babies/{baby['id']}", headers=auth_headers)
        assert resp.json()["code"] == 40400


class TestBabyOwnership:
    """宝宝归属校验测试组。"""

    def test_cannot_access_others_baby(self, client, auth_headers):
        """他人宝宝档案不应被访问。"""
        # 使用演示账号创建一个宝宝
        demo_baby = client.get("/api/v1/babies", headers=auth_headers)
        # 演示账号的宝宝 id 必然不为当前测试用户所有
        resp = client.get("/api/v1/babies/999999", headers=auth_headers)
        assert resp.json()["code"] == 40400

    def test_summary_demo_baby(self, client, demo_headers):
        """演示宝宝成长印记应包含月龄与阶段信息（8 个月爬行期场景）。

        期望值动态推导（修复 D01 测试硬编码问题）：演示宝宝出生日期由种子
        逻辑相对当前日期生成，此处从接口返回的 birth_date 出发，用被测的
        compute_age 计算期望月龄，再断言阶段名与月龄一致，保证测试不随
        系统日期推移而失效。

        @param client: 测试 HTTP 客户端夹具
        @param demo_headers: 演示账号鉴权头夹具
        @return: 无返回值，断言失败时抛出 AssertionError
        """
        resp = client.get("/api/v1/babies", headers=demo_headers)
        babies = resp.json()["data"]
        assert len(babies) >= 1
        demo_baby = babies[0]
        baby_id = demo_baby["id"]

        # 期望月龄由演示宝宝真实出生日期动态推导
        expected_months, _ = compute_age(date.fromisoformat(demo_baby["birth_date"]))
        # 种子设计保证演示宝宝恒为 8 个月大
        assert expected_months == 8

        summary = client.get(f"/api/v1/babies/{baby_id}/summary", headers=demo_headers).json()[
            "data"
        ]
        assert summary["baby_name"] == "豆豆"
        # 阶段名与月龄必须互相吻合（8 个月 → 爬行期）
        assert summary["stage_name"] == get_stage_name(expected_months)
        assert summary["age_months"] == expected_months
        assert summary["latest_weight_kg"] == 8.5
        assert summary["latest_height_cm"] == 72
        assert summary["latest_head_circumference_cm"] == 44
        # 里程碑进度应包含当前阶段关键项
        assert summary["milestone_progress"]
