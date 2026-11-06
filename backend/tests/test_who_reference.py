"""
@file: tests/test_who_reference.py
@description: WHO 2006 生长标准参考线测试：数据合法性单测与 growth-curve API 集成测试。
"""

from datetime import date

from app.services.growth import compute_age
from app.services.who_reference import WHO_MAX_MONTH, get_who_reference
from tests.conftest import create_test_baby

PERCENTILE_KEYS = ("p3", "p15", "p50", "p85", "p97")


class TestWhoReferenceData:
    """WHO 参考数据静态合法性测试组。"""

    def test_percentile_ordering_all_cases(self):
        """所有月龄/性别/指标的 P3 < P15 < P50 < P85 < P97 必须严格成立。"""
        for gender in ("male", "female"):
            ref = get_who_reference(gender, WHO_MAX_MONTH)
            for indicator in ("height", "weight"):
                for point in ref[indicator]:
                    values = [point[key] for key in PERCENTILE_KEYS]
                    assert values[0] < values[1] < values[2] < values[3] < values[4], (
                        f"{gender}/{indicator}/month={point['month']} 分位数顺序错误: {values}"
                    )

    def test_month_coverage_continuous(self):
        """0-24 月龄必须逐月连续覆盖（无缺月）。"""
        for gender in ("male", "female"):
            ref = get_who_reference(gender, WHO_MAX_MONTH)
            for indicator in ("height", "weight"):
                months = [p["month"] for p in ref[indicator]]
                assert months == list(range(WHO_MAX_MONTH + 1)), (
                    f"{gender}/{indicator} 月龄覆盖不连续"
                )

    def test_median_differs_between_genders(self):
        """男女孩中位数应不同（抽查 12 月龄）。"""
        male = get_who_reference("male", 12)
        female = get_who_reference("female", 12)
        assert male["weight"][12]["p50"] != female["weight"][12]["p50"]
        assert male["height"][12]["p50"] != female["height"][12]["p50"]

    def test_max_month_truncation(self):
        """max_month 应截断输出：列表只到 max_month 为止。"""
        ref = get_who_reference("female", 8)
        assert [p["month"] for p in ref["weight"]] == list(range(9))
        assert [p["month"] for p in ref["height"]] == list(range(9))


class TestGrowthCurveWhoReference:
    """growth-curve API 携带 WHO 参考线的集成测试组。"""

    def _create_baby(self, client, headers, name: str, gender: str, birth_date: str) -> dict:
        """通过 API 创建宝宝档案。

        @param client: 测试客户端
        @param headers: 鉴权头
        @param name: 宝宝昵称
        @param gender: 性别（male/female）
        @param birth_date: 出生日期（ISO 格式）
        @return: 创建成功后的宝宝数据字典
        """
        resp = client.post(
            "/api/v1/babies",
            headers=headers,
            json={"name": name, "gender": gender, "birth_date": birth_date},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    def _add_record(self, client, headers, baby_id):
        """为宝宝添加一条生长记录。

        @param client: 测试客户端
        @param headers: 鉴权头
        @param baby_id: 宝宝 ID
        @return: 无返回值
        """
        resp = client.post(
            f"/api/v1/babies/{baby_id}/growth-records",
            headers=headers,
            json={"record_date": "2026-08-01", "weight_kg": 8.5, "height_cm": 72},
        )
        assert resp.status_code == 200, resp.text

    def test_curve_contains_who_reference(self, client, auth_headers):
        """生长曲线响应应包含结构正确的 WHO 参考线。"""
        baby = create_test_baby(client, auth_headers)  # female, 2026-02-01
        self._add_record(client, auth_headers, baby["id"])
        resp = client.get(f"/api/v1/babies/{baby['id']}/growth-curve", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        who = data["who_reference"]
        assert who is not None
        # 覆盖上限 = min(24, 宝宝当前月龄 + 6)
        birth_date = date.fromisoformat(baby["birth_date"])
        expected_max = min(WHO_MAX_MONTH, compute_age(birth_date)[0] + 6)
        for indicator in ("height", "weight"):
            points = who[indicator]
            assert len(points) > 0
            # 月龄从 0 起连续覆盖，最后一格等于覆盖上限
            months = [p["month"] for p in points]
            assert months == list(range(expected_max + 1))
            # 每个点字段完整且分位数有序
            for p in points:
                values = [p[key] for key in PERCENTILE_KEYS]
                assert values[0] < values[1] < values[2] < values[3] < values[4]

    def test_curve_female_uses_girls_table(self, client, auth_headers):
        """female 宝宝应返回女孩标准数据（12 月龄女孩体重中位数 8.9kg、身长 74.0cm）。"""
        # 出生于 2025-06-01：任意运行日期下 max_month = 月龄+6 恒 >= 12（覆盖抽查月龄）
        baby = self._create_baby(client, auth_headers, "小美", "female", "2025-06-01")
        self._add_record(client, auth_headers, baby["id"])
        who = client.get(
            f"/api/v1/babies/{baby['id']}/growth-curve", headers=auth_headers
        ).json()["data"]["who_reference"]
        assert who is not None
        weight_12 = {p["month"]: p for p in who["weight"]}[12]
        height_12 = {p["month"]: p for p in who["height"]}[12]
        assert weight_12["p50"] == 8.9
        assert height_12["p50"] == 74.0

    def test_curve_male_uses_boys_table(self, client, auth_headers):
        """male 宝宝应返回男孩标准数据（12 月龄男孩体重中位数 9.6kg、身长 75.7cm）。"""
        baby = self._create_baby(client, auth_headers, "小安", "male", "2025-06-01")
        self._add_record(client, auth_headers, baby["id"])
        who = client.get(
            f"/api/v1/babies/{baby['id']}/growth-curve", headers=auth_headers
        ).json()["data"]["who_reference"]
        assert who is not None
        weight_12 = {p["month"]: p for p in who["weight"]}[12]
        height_12 = {p["month"]: p for p in who["height"]}[12]
        assert weight_12["p50"] == 9.6
        assert height_12["p50"] == 75.7

    def test_curve_over_24_months_returns_none(self, client, auth_headers):
        """超过 24 月龄的宝宝不返回 WHO 参考线（数据范围所限，who_reference 为 null）。"""
        baby = self._create_baby(client, auth_headers, "大哥", "male", "2023-01-01")
        self._add_record(client, auth_headers, baby["id"])
        data = client.get(
            f"/api/v1/babies/{baby['id']}/growth-curve", headers=auth_headers
        ).json()["data"]
        assert data["who_reference"] is None
