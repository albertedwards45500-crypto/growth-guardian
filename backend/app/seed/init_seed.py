"""
@file: app/seed/init_seed.py
@description: 种子数据初始化脚本：幂等写入食谱、指南与 FAQ，并创建演示账号与演示宝宝。
             演示宝宝的出生日期与生长记录、里程碑、饮食记录日期均相对当前日期生成，
             保证"8 个月大、爬行期"的演示语义不随系统日期推移而漂移（修复缺陷 D01）。
             同时内置"演示数据自愈刷新"机制：每次启动检查存量演示宝宝，若其月龄
             已偏离 8 个月（含旧版固定出生日期 2025-12-10 的历史数据，或早期以
             相对逻辑生成、随时间自然漂移的数据），则删除并按新逻辑重建，根治
             演示数据随时间腐化的问题。
"""

import calendar
import logging
from datetime import date, timedelta

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.advice import Faq, Guide
from app.models.baby import Baby
from app.models.diet import DietRecord
from app.models.growth import GrowthRecord, Milestone
from app.models.recipe import Recipe
from app.models.user import User
from app.seed.faqs_data import FAQS_DATA
from app.seed.guides_data import GUIDES_DATA
from app.seed.recipes_data import RECIPES_DATA
from app.services.growth import compute_age

logger = logging.getLogger("baby_growth")


def _shift_months(d: date, months: int) -> date:
    """按自然月平移日期（月末安全）。

    目标月不存在同日号时（例如 1 月 31 日回退 1 个月到 2 月），截断为
    目标月最后一天，等价于 dateutil.relativedelta 的月末语义。

    @param d: 基准日期
    @param months: 平移月数，负数表示向过去回退
    @return: 平移后的日期
    """
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _demo_birth_date(today: date | None = None) -> date:
    """计算演示宝宝出生日期：当前日期回退 8 个自然月。

    修复缺陷 D01：原实现硬编码 date(2025, 12, 10)，随系统日期推移月龄漂移，
    导致"8 个月爬行期"演示场景及 tests/test_babies.py、tests/test_recipes.py
    中的相关断言失效。改为相对当前日期生成后，无论何时初始化种子，
    演示宝宝月龄恒为 8 个月（爬行期）。
    注：python-dateutil 未纳入项目依赖，此处以手写月份回退逻辑实现等价语义。

    @param today: 计算基准日期，缺省取当前系统日期
    @return: 演示宝宝出生日期（today 回退 8 个月，月末自动截断）
    """
    return _shift_months(today or date.today(), -8)


def seed_all() -> None:
    """执行全部种子数据写入（幂等：已存在则不重复写入）。

    @return: 无返回值
    """
    with SessionLocal() as db:
        _seed_recipes(db)
        _seed_guides(db)
        _seed_faqs(db)
        _seed_demo_user(db)
        db.commit()


def _seed_recipes(db) -> None:
    """写入初始食谱数据。

    @param db: 数据库会话
    """
    existing = db.query(Recipe).count()
    if existing > 0:
        return
    for item in RECIPES_DATA:
        db.add(Recipe(**item))
    logger.info("已写入 %d 条食谱", len(RECIPES_DATA))


def _seed_guides(db) -> None:
    """写入分月龄指南数据。

    @param db: 数据库会话
    """
    existing = db.query(Guide).count()
    if existing > 0:
        return
    for item in GUIDES_DATA:
        db.add(Guide(**item))
    logger.info("已写入 %d 条喂养指南", len(GUIDES_DATA))


def _seed_faqs(db) -> None:
    """写入常见问题知识库数据。

    @param db: 数据库会话
    """
    existing = db.query(Faq).count()
    if existing > 0:
        return
    for item in FAQS_DATA:
        db.add(Faq(**item))
    logger.info("已写入 %d 条常见问题", len(FAQS_DATA))


def _seed_demo_user(db) -> None:
    """创建演示账号（手机号 13800000000 / 密码 123456）及演示宝宝数据（含自愈刷新）。

    处理逻辑分两条路径：
    - 演示账号不存在：创建账号后按相对日期逻辑新建演示宝宝与全部记录；
    - 演示账号已存在：执行"演示数据自愈刷新"检查（见下），否则不动（幂等）。

    演示数据自愈刷新（修复缺陷 D01 的收尾，根治"演示数据随时间腐化"）：
    每次启动检查存量演示宝宝"豆豆"，满足任一条件即删除重建——
    1. 按 compute_age 口径计算的月龄不等于 8 个月：既覆盖旧版以固定日期
       2025-12-10 创建的历史数据（当前会呈现"满 10 月龄/扶站期"），也覆盖
       早期以相对逻辑生成、随系统日期自然漂移出 8 个月的存量数据；
    2. 出生日期仍为旧版固定日期 date(2025, 12, 10)（防御性兜底，确保旧数据
       无论漂移与否都会被刷新）。
    重建使用与新建完全相同的相对日期逻辑，保证任何时点启动后演示数据均呈现
    "8 个月/爬行期"设计稿语义。

    @param db: 数据库会话（事务由调用方 seed_all 统一 commit）
    @raises sqlalchemy.exc.SQLAlchemyError: 底层数据库读写失败时抛出，由上层处理
    """
    demo_phone = "13800000000"
    user = db.query(User).filter(User.phone == demo_phone).first()
    if user is None:
        user = User(
            phone=demo_phone,
            nickname="豆豆妈妈",
            password_hash=hash_password("123456"),
        )
        db.add(user)
        db.flush()
        _create_demo_baby_with_records(db, user.id)
        logger.info("已创建演示账号 %s（密码 123456）与演示宝宝", demo_phone)
        return

    # —— 演示数据自愈刷新检查 ——
    # 仅匹配演示宝宝"豆豆"；若该宝宝已被删除（如演示过程中被人工清理），
    # 不做重建，避免覆盖演示账号下用户的自建数据。
    baby = db.query(Baby).filter(Baby.user_id == user.id, Baby.name == "豆豆").first()
    if baby is None:
        return
    months = compute_age(baby.birth_date)[0]
    # 统一自愈条件：月龄漂移（≠8 个月）或仍为旧版固定出生日期 → 删除重建
    if months != 8 or baby.birth_date == date(2025, 12, 10):
        logger.info(
            "检测到演示宝宝数据过期（birth_date=%s，月龄 %d 个月），执行自愈刷新重建",
            baby.birth_date,
            months,
        )
        # Baby 模型关联关系配置了 cascade="all, delete-orphan"，且子表外键均为
        # ondelete="CASCADE"，db.delete 可可靠级联清除生长记录/里程碑/饮食记录等
        db.delete(baby)
        db.flush()
        _create_demo_baby_with_records(db, user.id)
        logger.info("演示宝宝已按当前日期重建（8 个月/爬行期）")


def _create_demo_baby_with_records(db, user_id: int) -> Baby:
    """创建演示宝宝"豆豆"及其生长记录、里程碑、饮食记录（新建与自愈刷新共用）。

    演示宝宝对齐设计稿语义：8 个月爬行期，体重 8.5kg、身高 72cm、头围 44cm，
    含母乳喂养与南瓜泥辅食记录。

    日期口径（修复缺陷 D01）：出生日期 = 当前日期回退 8 个月；生长记录、
    里程碑、饮食记录日期均按"相对出生日的天数偏移"生成，偏移量取自原
    设计稿日期相对原出生日 2025-12-10 的间隔（最近测量 234 天 / 203 天 /
    173 天，翻身 161 天、独坐 207 天、爬行 234 天，饮食动态 234 天）。
    自然月回退 8 个月的跨度至少 242 天，因此最大偏移 234 天的业务日期
    恒早于当前日期至少 8 天，不会出现"未来日期"，且最近一次测量距今天
    较近，保持原"最近动态"语义。

    @param db: 数据库会话
    @param user_id: 演示宝宝归属的用户 ID
    @return: 已写入会话（flush 未 commit）的演示宝宝对象
    @raises sqlalchemy.exc.SQLAlchemyError: 底层数据库写入失败时抛出，由上层处理
    """
    # 出生日期相对当前日期生成（修复 D01），月龄恒为 8 个月
    birth_date = _demo_birth_date()

    def offset_day(days: int) -> date:
        """基于演示宝宝出生日期偏移指定天数，生成业务记录日期。

        @param days: 相对出生日的天数偏移（正数表示出生之后）
        @return: 业务记录日期
        """
        return birth_date + timedelta(days=days)

    baby = Baby(
        user_id=user_id,
        name="豆豆",
        gender="male",
        birth_date=birth_date,
        is_default=True,
    )
    db.add(baby)
    db.flush()

    # 生长记录（对齐设计稿最近测量数据；偏移天数对应原稿 6/1、7/1、8/1 三次测量）
    db.add_all(
        [
            GrowthRecord(baby_id=baby.id, record_date=offset_day(234), weight_kg=8.5, height_cm=72, head_circumference_cm=44),
            GrowthRecord(baby_id=baby.id, record_date=offset_day(203), weight_kg=8.0, height_cm=70, head_circumference_cm=43.5),
            GrowthRecord(baby_id=baby.id, record_date=offset_day(173), weight_kg=7.4, height_cm=68, head_circumference_cm=42.5),
        ]
    )
    # 里程碑（偏移天数对应原稿 5/20、7/5、8/1）
    db.add_all(
        [
            Milestone(baby_id=baby.id, milestone_type="roll_over", name="翻身", achieved_at=offset_day(161)),
            Milestone(baby_id=baby.id, milestone_type="sit", name="独坐", achieved_at=offset_day(207)),
            Milestone(baby_id=baby.id, milestone_type="crawl", name="爬行", achieved_at=offset_day(234)),
        ]
    )
    # 饮食记录（对齐设计稿"最近动态"，与最近一次测量同日，距今天较近）
    db.add_all(
        [
            DietRecord(
                baby_id=baby.id,
                record_date=offset_day(234),
                record_type="breast_milk",
                details={"left_minutes": 15, "right_minutes": 10},
                note="宝宝吃得很好，之后很快入睡",
            ),
            DietRecord(
                baby_id=baby.id,
                record_date=offset_day(234),
                record_type="solid_food",
                details={"food_items": ["南瓜泥"]},
                note="首次尝试南瓜泥，吃了一小勺，表情很惊喜，没有排斥反应",
            ),
        ]
    )
    return baby
