"""
@file: tests/test_migrations.py
@description: Alembic 迁移测试（审计缺陷 D05）。在独立的临时 SQLite 文件库上验证：
             upgrade head 建齐 12 张表、数据库级唯一约束生效、downgrade base 清表、
             升级-回滚-再升级幂等往返，以及重复 upgrade 不破坏存量数据。

URL 覆盖方式说明：app.core.config.Settings 为 lru_cache 模块级单例，进程内难以
替换，故 migrations/env.py 支持 URL 注入——命令行用 `-x db_url=...`，进程内
alembic.command API 调用则向 alembic_cfg.attributes["db_url"] 写入（本测试采用）。
测试全程不触碰 conftest.py 的内存库与 app.engine，互不污染。
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import BASE_DIR

# 迁移完成后应存在的 12 张业务表
EXPECTED_TABLES = {
    "users",
    "babies",
    "growth_records",
    "milestones",
    "diet_records",
    "allergies",
    "recipes",
    "recipe_favorites",
    "meal_plans",
    "guides",
    "faqs",
    "notifications",
}


def _make_alembic_config(db_path) -> Config:
    """构建指向指定 SQLite 文件库的 Alembic 配置，并注入数据库 URL。

    @param db_path: SQLite 数据库文件路径（tmp_path 下）
    @return: 已注入 script_location（绝对路径）与 attributes["db_url"] 的 Alembic Config
    """
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    # 绝对路径指定迁移脚本目录，避免受 pytest 启动时工作目录影响
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    # URL 注入：env.py 优先读取 attributes["db_url"]，从而完全绕开 settings 单例
    cfg.attributes["db_url"] = f"sqlite:///{db_path.as_posix()}"
    return cfg


def _connect(db_path) -> sqlite3.Connection:
    """建立原生 sqlite3 连接并开启外键强制（SQLite 默认关闭，需逐连接开启）。

    @param db_path: SQLite 数据库文件路径
    @return: 已开启 PRAGMA foreign_keys=ON 的连接
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _last_insert_id(conn: sqlite3.Connection) -> int:
    """读取当前连接最近一次插入的自增主键。

    @param conn: SQLite 连接
    @return: 最近插入行的 rowid
    """
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_parent_rows(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """插入 user / recipe / baby 最小父记录，供收藏与计划槽位约束测试引用。

    ORM 级 default（如 is_active）不落库为服务器默认值，故逐列显式赋值。

    @param conn: SQLite 连接（需已开启外键）
    @return: (user_id, recipe_id, baby_id) 三元组
    """
    conn.execute(
        "INSERT INTO users (phone, nickname, password_hash, is_active) VALUES (?, ?, ?, 1)",
        ("13900009999", "迁移测试家长", "x" * 60),
    )
    user_id = _last_insert_id(conn)
    conn.execute(
        "INSERT INTO recipes (title, suitable_age_min, suitable_age_max, "
        "ingredients, steps, nutrition_tags, is_active) VALUES (?, 6, 36, '[]', '[]', '[]', 1)",
        ("迁移测试食谱",),
    )
    recipe_id = _last_insert_id(conn)
    conn.execute(
        "INSERT INTO babies (user_id, name, birth_date, is_default) VALUES (?, ?, '2026-02-01', 0)",
        (user_id, "迁移测试宝宝"),
    )
    baby_id = _last_insert_id(conn)
    conn.commit()
    return user_id, recipe_id, baby_id


@pytest.fixture()
def migration_env(tmp_path):
    """提供独立临时 SQLite 文件库与对应 Alembic 配置，测试结束后自动清理文件。

    @param tmp_path: pytest 临时目录夹具
    @yield: (AlembicConfig, 数据库文件 Path) 二元组
    """
    db_path = tmp_path / "migration_test.db"
    yield _make_alembic_config(db_path), db_path
    if db_path.exists():
        db_path.unlink()


def test_upgrade_head_creates_all_12_tables(migration_env):
    """upgrade head 后 sqlite_master 中应存在全部 12 张业务表。

    @param migration_env: 迁移测试环境夹具
    @return: 无返回值，断言失败时抛出 AssertionError
    """
    cfg, db_path = migration_env
    command.upgrade(cfg, "head")
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in rows}
    finally:
        conn.close()
    missing = EXPECTED_TABLES - names
    assert not missing, f"upgrade head 后缺少数据表: {sorted(missing)}"


def test_unique_constraints_enforced(migration_env):
    """数据库级唯一约束应生效：重复收藏与重复计划槽位均被 IntegrityError 拒绝。

    前置数据（user/recipe/baby）已提交，重复插入在独立语句上触发约束。

    @param migration_env: 迁移测试环境夹具
    @return: 无返回值，断言失败时抛出 AssertionError
    """
    cfg, db_path = migration_env
    command.upgrade(cfg, "head")
    conn = _connect(db_path)
    try:
        user_id, recipe_id, baby_id = _insert_parent_rows(conn)

        # 首次收藏成功
        conn.execute(
            "INSERT INTO recipe_favorites (user_id, recipe_id) VALUES (?, ?)",
            (user_id, recipe_id),
        )
        conn.commit()
        # 同一用户重复收藏同一食谱：uq_recipe_favorites_user_recipe 约束拒绝
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO recipe_favorites (user_id, recipe_id) VALUES (?, ?)",
                (user_id, recipe_id),
            )
        conn.rollback()

        # 同一槽位（宝宝×周×星期×餐次）首次保存成功
        conn.execute(
            "INSERT INTO meal_plans (baby_id, week_start, day_of_week, meal_type) "
            "VALUES (?, '2026-03-02', 0, 'breakfast')",
            (baby_id,),
        )
        conn.commit()
        # 相同槽位再次保存：uq_meal_plans_slot 约束拒绝
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO meal_plans (baby_id, week_start, day_of_week, meal_type) "
                "VALUES (?, '2026-03-02', 0, 'breakfast')",
                (baby_id,),
            )
        conn.rollback()
    finally:
        conn.close()


def test_downgrade_base_drops_all_tables(migration_env):
    """downgrade base 后 12 张业务表应全部删除（alembic_version 由工具自身管理，不校验）。

    @param migration_env: 迁移测试环境夹具
    @return: 无返回值，断言失败时抛出 AssertionError
    """
    cfg, db_path = migration_env
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in rows}
    finally:
        conn.close()
    assert not (EXPECTED_TABLES & names), f"downgrade base 后仍有残留表: {sorted(EXPECTED_TABLES & names)}"


def test_upgrade_downgrade_upgrade_roundtrip(migration_env):
    """升级 → 回滚到 base → 再次升级应全部成功（幂等往返）。

    @param migration_env: 迁移测试环境夹具
    @return: 无返回值，执行失败时抛出异常
    """
    cfg, _ = migration_env
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    # 再次升级：验证迁移可重复执行（例如全新环境重复部署）
    command.upgrade(cfg, "head")


def test_rerun_upgrade_preserves_data(migration_env):
    """已是 head 时再次执行 upgrade head 应为无操作，且存量数据不被破坏。

    @param migration_env: 迁移测试环境夹具
    @return: 无返回值，断言失败时抛出 AssertionError
    """
    cfg, db_path = migration_env
    command.upgrade(cfg, "head")

    # 插入一行用户数据
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (phone, nickname, password_hash, is_active) VALUES (?, ?, ?, 1)",
            ("13900001234", "存量数据用户", "y" * 60),
        )
        conn.commit()
    finally:
        conn.close()

    # 再次 upgrade head：已处于最新版本，无任何 DDL 操作
    command.upgrade(cfg, "head")

    # 存量数据应原样保留
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT phone, nickname FROM users WHERE phone = ?", ("13900001234",)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "重复 upgrade head 后用户数据丢失"
    assert row == ("13900001234", "存量数据用户")
