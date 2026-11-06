"""
@file: app/services/growth.py
@description: 成长记录业务服务：月龄计算、发育阶段判定、成长印记聚合与生长曲线构建。
"""

import calendar
from datetime import date

from sqlalchemy.orm import Session

from app.models.baby import Baby
from app.models.growth import GrowthRecord, Milestone
from app.schemas.growth import CurvePoint, GrowthCurveResponse, GrowthSummary
from app.services.who_reference import WHO_MAX_MONTH, get_who_reference

# 发育阶段定义（月龄区间 -> 阶段名称）
STAGES: list[tuple[int, int, str]] = [
    (0, 2, "新生儿期"),
    (3, 5, "翻身期"),
    (6, 8, "爬行期"),
    (9, 11, "扶站期"),
    (12, 17, "行走期"),
    (18, 23, "跑跳期"),
    (24, 36, "探索期"),
]

# 各阶段关键里程碑类型
MILESTONE_TYPES: dict[str, str] = {
    "roll_over": "翻身",
    "sit": "独坐",
    "crawl": "爬行",
    "stand": "扶站",
    "walk": "行走",
    "run": "跑跳",
    "talk": "说话",
}


def compute_age(birth_date: date, on: date | None = None) -> tuple[int, int]:
    """计算宝宝月龄与超出整月的剩余天数（修复缺陷 D14 的跨月借位口径）。

    口径说明：
    - 整月数 months：先按"年差 × 12 + 月差"得到粗月龄；若目标日号小于出生
      日号（target.day < birth_date.day），说明本月尚未"满月"，months 减 1。
    - 余数天数 days：目标日期减去"锚点日"。锚点日的取法：
      * 当 target.day >= birth_date.day 时，锚点即目标当月的出生同日
        （该日必然存在：birth_date.day <= target.day 且 target.day 是当月
        合法日期）；
      * 当 target.day < birth_date.day 时，锚点回退到上一个自然月的"出生
        同日"，若上个月没有该日号（例如出生日 31 日而上月只有 30 或 28 天），
        则取上月最后一天，days = (target - 锚点).days。
    - 结果钳制为非负：返回 (max(months, 0), max(days, 0))。
    - 防御：on 早于出生日期（脏数据）时直接返回 (0, 0)，不抛异常。

    月末边界示例（birth=2026-01-31，2026 年 2 月仅 28 天）：
    - on=2026-02-28 → (0, 28)：2 月不存在 31 日，按"日号未达到出生日号"
      口径尚不满 1 个月，days 为距出生日的自然日差；
    - on=2026-03-01 → (1, 1)：锚点回退到上月最后一天 2026-02-28，超出 1 天。

    @param birth_date: 出生日期
    @param on: 计算基准日期，缺省取当前系统日期
    @return: (整月数, 超出整月的天数)，两者均不小于 0；on 早于出生日期时返回 (0, 0)
    """
    target = on or date.today()
    if target < birth_date:
        # 防御：观测日期早于出生日期，按 0 月 0 天处理
        return 0, 0
    months = (target.year - birth_date.year) * 12 + (target.month - birth_date.month)
    if target.day < birth_date.day:
        # 本月尚未到"出生同日"，未满整月：月龄减一并回退锚点到上一个自然月
        months -= 1
        if target.month == 1:
            prev_year, prev_month = target.year - 1, 12
        else:
            prev_year, prev_month = target.year, target.month - 1
        # 上月没有出生同日号时（31 日出生、上月只有 30/28 天）取上月最后一天
        anchor_day = min(birth_date.day, calendar.monthrange(prev_year, prev_month)[1])
        anchor = date(prev_year, prev_month, anchor_day)
    else:
        anchor = date(target.year, target.month, birth_date.day)
    days = (target - anchor).days
    return max(months, 0), max(days, 0)


def get_stage_name(age_months: int) -> str:
    """根据月龄获取发育阶段名称。

    @param age_months: 宝宝月龄
    @return: 阶段名称；超出定义范围时返回最近阶段
    """
    for start, end, name in STAGES:
        if start <= age_months <= end:
            return name
    return STAGES[0][2] if age_months < STAGES[0][0] else STAGES[-1][2]


def build_growth_summary(db: Session, baby: Baby) -> GrowthSummary:
    """构建成长印记聚合数据（首页核心视觉）。

    @param db: 数据库会话
    @param baby: 宝宝档案
    @return: GrowthSummary 聚合模型
    """
    age_months, age_days = compute_age(baby.birth_date)

    latest = (
        db.query(GrowthRecord)
        .filter(GrowthRecord.baby_id == baby.id)
        .order_by(GrowthRecord.record_date.desc(), GrowthRecord.id.desc())
        .first()
    )

    # 当前阶段关键里程碑达成情况
    progress: dict[str, int] = {}
    achieved = {
        m.milestone_type
        for m in db.query(Milestone).filter(Milestone.baby_id == baby.id).all()
    }
    stage_start, stage_end, _ = _find_stage_range(age_months)
    for mtype, name in MILESTONE_TYPES.items():
        # 只统计当前阶段及之前阶段的里程碑
        if _milestone_stage_index(mtype) <= stage_end:
            progress[f"{mtype}_{name}"] = 1 if mtype in achieved else 0

    return GrowthSummary(
        baby_id=baby.id,
        baby_name=baby.name,
        age_months=age_months,
        age_days=age_days,
        stage_name=get_stage_name(age_months),
        latest_weight_kg=latest.weight_kg if latest else None,
        latest_height_cm=latest.height_cm if latest else None,
        latest_head_circumference_cm=latest.head_circumference_cm if latest else None,
        latest_measure_date=latest.record_date if latest else None,
        milestone_progress=progress,
    )


def build_growth_curve(db: Session, baby: Baby) -> GrowthCurveResponse:
    """构建生长曲线数据（按时间升序，附带月龄坐标）。

    @param db: 数据库会话
    @param baby: 宝宝档案
    @return: GrowthCurveResponse 曲线数据
    """
    records = (
        db.query(GrowthRecord)
        .filter(GrowthRecord.baby_id == baby.id)
        .order_by(GrowthRecord.record_date.asc())
        .all()
    )
    weight_series: list[CurvePoint] = []
    height_series: list[CurvePoint] = []
    head_series: list[CurvePoint] = []

    for rec in records:
        age_months, _ = compute_age(baby.birth_date, rec.record_date)
        base = CurvePoint(record_date=rec.record_date, age_months=age_months)
        if rec.weight_kg is not None:
            weight_series.append(base.model_copy(update={"weight_kg": rec.weight_kg}))
        if rec.height_cm is not None:
            height_series.append(base.model_copy(update={"height_cm": rec.height_cm}))
        if rec.head_circumference_cm is not None:
            head_series.append(base.model_copy(update={"head_circumference_cm": rec.head_circumference_cm}))

    # WHO 2006 参考线：数据仅覆盖 0-24 月龄，超过 24 月龄的宝宝不返回参考线
    current_age_months, _ = compute_age(baby.birth_date)
    who_reference = None
    if current_age_months <= WHO_MAX_MONTH:
        # 覆盖当前月龄 + 6，且至少到最新一条记录的月龄；上限 24 月以匹配 WHO 数据范围
        latest_age_months = max(
            (compute_age(baby.birth_date, r.record_date)[0] for r in records), default=0
        )
        max_month = min(WHO_MAX_MONTH, max(current_age_months + 6, latest_age_months))
        who_reference = get_who_reference(baby.gender, max_month)

    return GrowthCurveResponse(
        baby_id=baby.id,
        weight_series=weight_series,
        height_series=height_series,
        head_circumference_series=head_series,
        who_reference=who_reference,
    )


def _find_stage_range(age_months: int) -> tuple[int, int, str]:
    """查找月龄所在阶段区间。

    @param age_months: 宝宝月龄
    @return: (起始月龄, 结束月龄, 阶段名称)
    """
    for start, end, name in STAGES:
        if start <= age_months <= end:
            return start, end, name
    return STAGES[-1]


def _milestone_stage_index(mtype: str) -> int:
    """获取里程碑类型所属阶段索引（用于进度统计）。

    @param mtype: 里程碑类型编码
    @return: 阶段索引（0 起）
    """
    mapping = {
        "roll_over": 1,
        "sit": 2,
        "crawl": 2,
        "stand": 3,
        "walk": 4,
        "run": 5,
        "talk": 4,
    }
    return mapping.get(mtype, 2)
