"""
@file: tests/test_unit_growth.py
@description: compute_age / get_stage_name 纯函数单元测试（修复缺陷 D14 后的口径回归）。
             不依赖数据库，重点覆盖月末出生、闰年 2 月、当天出生、防御输入与阶段边界。
"""

from datetime import date

import pytest

from app.services.growth import compute_age, get_stage_name


class TestComputeAgeBasics:
    """compute_age 基础语义测试组。"""

    @pytest.mark.parametrize(
        "birth,on,expected",
        [
            # 同一天出生：整月数 0、余数天数 0
            (date(2026, 5, 10), date(2026, 5, 10), (0, 0)),
            # 普通整月：同日号即满整月，days 为 0
            (date(2026, 1, 10), date(2026, 3, 10), (2, 0)),
            # 普通跨月借位：3-10 观测 1-15 出生，未到 15 日故 1 个月，
            # 锚点回退到 2-15，days = (3-10 - 2-15) = 23
            (date(2026, 1, 15), date(2026, 3, 10), (1, 23)),
            # 跨年借位（目标 1 月、出生 12 月）：months 从 1 借位为 0，
            # 锚点 2025-12-10，days = (2026-01-05 - 2025-12-10) = 26
            (date(2025, 12, 10), date(2026, 1, 5), (0, 26)),
        ],
    )
    def test_basic_cases(self, birth, on, expected):
        """基础月龄计算应与推导的期望值一致。

        @param birth: 出生日期（parametrize 提供）
        @param on: 观测日期（parametrize 提供）
        @param expected: 期望的 (月龄, 余数天数)（parametrize 提供）
        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(birth, on) == expected


class TestComputeAgeMonthEnd:
    """compute_age 月末出生边界测试组（D14 修复重点）。"""

    def test_month_end_birth_feb28(self):
        """1-31 出生、2-28 观测应为 (0, 28)。

        期望依据：2026 年 2 月不存在 31 日，按"目标日号未达到出生日号"
        口径尚不满 1 个月，故 months=0；days 为距出生日的自然日差 28。
        结果无负数且语义自洽（次日 3-1 起才算满月）。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(date(2026, 1, 31), date(2026, 2, 28)) == (0, 28)

    def test_month_end_birth_mar1(self):
        """1-31 出生、3-1 观测应为 (1, 1)。

        期望依据：1 < 31 触发借位，锚点回退到上月（2 月）最后一天
        2026-02-28（min(31, 28)），days = (3-1 - 2-28) = 1，months = 1。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(date(2026, 1, 31), date(2026, 3, 1)) == (1, 1)

    def test_month_end_birth_mar31_and_mar30(self):
        """1-31 出生在 3-30 / 3-31 观测应分别为 (1, 30) 与 (2, 0)。

        期望依据：3-30 日号 30 < 31 借位，锚点 2026-02-28，days=30；
        3-31 日号达到 31，恰好满 2 个月，days=0。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(date(2026, 1, 31), date(2026, 3, 30)) == (1, 30)
        assert compute_age(date(2026, 1, 31), date(2026, 3, 31)) == (2, 0)

    def test_old_borrow_bug_regression(self):
        """旧实现借位偏差回归：1-15 出生、3-14 观测应为 (1, 27) 而非 (1, 31)。

        期望依据：锚点回退到 2026-02-15，days = 27。旧实现错误地按
        "目标当月天数 + 1" 借位，会得到 (1, 31)——余数天数超过上月
        实际长度 28 天，口径明显不自洽。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        months, days = compute_age(date(2026, 1, 15), date(2026, 3, 14))
        assert (months, days) == (1, 27)
        # 余数天数必须小于借位月的实际长度（28 天），否则口径错误
        assert days < 28


class TestComputeAgeLeapYear:
    """compute_age 闰年 2 月边界测试组。"""

    def test_feb29_birth_across_leap_boundary(self):
        """闰日 2024-02-29 出生在关键日期观测的结果应正确。

        期望依据：
        - on=2024-03-31 → (1, 2)：日号 31 >= 29 满 1 个月，锚点 3-29；
        - on=2025-02-28 → (11, 30)：28 < 29 借位，锚点回退到 2025-01-29
          （上月 31 天，29 日存在），days = 30，次日才满 12 个月；
        - on=2025-03-01 → (12, 1)：锚点回退到 2025-02-28（平年 2 月末，
          min(29, 28)），days = 1；
        - on=2025-03-29 → (13, 0)：日号 29 达到出生日号，恰好 13 个月。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(date(2024, 2, 29), date(2024, 3, 31)) == (1, 2)
        assert compute_age(date(2024, 2, 29), date(2025, 2, 28)) == (11, 30)
        assert compute_age(date(2024, 2, 29), date(2025, 3, 1)) == (12, 1)
        assert compute_age(date(2024, 2, 29), date(2025, 3, 29)) == (13, 0)

    def test_feb28_birth_around_feb(self):
        """平年 2025-02-28 出生在 2 月前后的观测结果应正确。

        期望依据：
        - on=2025-03-31 → (1, 3)：31 >= 28 满 1 个月，锚点 3-28；
        - on=2026-02-28 → (12, 0)：日号 28 达到出生日号，恰好满 12 个月；
        - on=2026-03-01 → (12, 1)：1 < 28 借位，锚点 2026-02-28，days=1。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(date(2025, 2, 28), date(2025, 3, 31)) == (1, 3)
        assert compute_age(date(2025, 2, 28), date(2026, 2, 28)) == (12, 0)
        assert compute_age(date(2025, 2, 28), date(2026, 3, 1)) == (12, 1)


class TestComputeAgeDefensive:
    """compute_age 防御输入测试组。"""

    def test_same_day_birth(self):
        """当天出生应返回 (0, 0)。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(date(2026, 5, 10), date(2026, 5, 10)) == (0, 0)

    def test_on_before_birth_returns_zero_zero(self):
        """观测日期早于出生日期（脏数据）应返回 (0, 0) 且不抛异常。

        实现语义：显式防御分支 target < birth_date 时直接返回 (0, 0)，
        避免借位逻辑对负时间差产生无意义结果。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert compute_age(date(2026, 5, 10), date(2026, 5, 1)) == (0, 0)
        assert compute_age(date(2026, 5, 10), date(2025, 1, 1)) == (0, 0)


class TestComputeAgeDeterminism:
    """compute_age 确定性测试组。"""

    def test_explicit_on_is_deterministic(self):
        """显式传入 on 时结果应为常量，不依赖 date.today()。

        期望依据：birth=2025-12-10、on=2026-08-01 时，8 月 1 < 10 借位，
        锚点 2026-07-10，days=22，故恒为 (7, 22)；观测日期后移一天结果
        相应变化，证明输出由 on 决定而非系统当前时间。

        @return: 无返回值，断言失败时抛出 AssertionError
        """
        birth = date(2025, 12, 10)
        assert compute_age(birth, on=date(2026, 8, 1)) == (7, 22)
        # 同参数重复调用结果一致
        assert compute_age(birth, on=date(2026, 8, 1)) == compute_age(birth, on=date(2026, 8, 1))
        # on 变化一天，结果随之变化（结果由 on 驱动）
        assert compute_age(birth, on=date(2026, 8, 2)) == (7, 23)


class TestStageNameBoundaries:
    """get_stage_name 阶段边界归属测试组。"""

    @pytest.mark.parametrize(
        "age_months,expected",
        [
            (2, "新生儿期"),   # STAGES: 0-2
            (3, "翻身期"),     # STAGES: 3-5
            (5, "翻身期"),
            (6, "爬行期"),     # STAGES: 6-8
            (8, "爬行期"),
            (9, "扶站期"),     # STAGES: 9-11
            (11, "扶站期"),
            (12, "行走期"),    # STAGES: 12-17
            (36, "探索期"),    # STAGES: 24-36
            (37, "探索期"),    # 超出上限归入最后阶段
        ],
    )
    def test_stage_boundaries(self, age_months, expected):
        """各月龄边界值应归属正确的发育阶段。

        @param age_months: 月龄（parametrize 提供）
        @param expected: 期望的阶段名称（parametrize 提供）
        @return: 无返回值，断言失败时抛出 AssertionError
        """
        assert get_stage_name(age_months) == expected
