"""
@file: tests/test_advice.py
@description: 专业建议模块集成测试：分月龄指南匹配与 FAQ 检索。
"""


class TestGuide:
    """分月龄指南测试组。"""

    def test_guide_by_month(self, client, auth_headers):
        """8 个月应匹配爬行期指南。"""
        resp = client.get("/api/v1/advice/guides", headers=auth_headers, params={"month": 8})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data is not None
        assert data["month_start"] == 6
        assert data["month_end"] == 8

    def test_guide_for_newborn(self, client, auth_headers):
        """1 个月应匹配新生儿期指南。"""
        resp = client.get("/api/v1/advice/guides", headers=auth_headers, params={"month": 1})
        assert resp.json()["data"]["title"].startswith("新生儿期")


class TestFaq:
    """常见问题检索测试组。"""

    def test_search_by_keyword(self, client, auth_headers):
        """按关键词检索 FAQ。"""
        resp = client.get(
            "/api/v1/advice/faqs", headers=auth_headers, params={"keyword": "便秘"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) > 0
        # 结果应包含与便秘相关的内容
        joined = " ".join(f"{f['question']} {f['answer']}" for f in data)
        assert "便秘" in joined

    def test_filter_by_category(self, client, auth_headers):
        """按分类过滤 FAQ。"""
        resp = client.get(
            "/api/v1/advice/faqs", headers=auth_headers, params={"category": "allergy"}
        )
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(f["category"] == "allergy" for f in data)

    def test_list_all_faqs(self, client, auth_headers):
        """无参数应返回全部 FAQ。"""
        resp = client.get("/api/v1/advice/faqs", headers=auth_headers)
        assert len(resp.json()["data"]) >= 10
