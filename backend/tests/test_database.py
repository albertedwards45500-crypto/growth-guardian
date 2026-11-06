"""
@file: tests/test_database.py
@description: 数据库层完整性测试：唯一约束（D07）、级联删除与一周计划事务回滚保护。
"""

from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, engine
from app.models.baby import Baby
from app.models.diet import DietRecord
from app.models.recipe import MealPlan, RecipeFavorite
from app.models.user import User
from tests.conftest import create_test_baby

# 测试专用隔离用户手机号（不与 conftest 的 13900000001 / 演示账号 13800000000 冲突）
ISOLATED_PHONE = "13900000077"


# D07 的事务回滚与 DB 级级联用例依赖 SQLite 外键强制；conftest 引擎对内存库使用
# StaticPool 单连接共享，故在模块收集阶段（早于任何连接建立）注册 connect 事件，
# 对进程内唯一连接统一开启 PRAGMA foreign_keys=ON。
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_conn, _record):
    """为每个新建 DBAPI 连接开启 SQLite 外键强制。

    @param dbapi_conn: 底层 DBAPI 连接
    @param _record: 连接事件记录（未使用）
    @return: 无返回值，副作用为连接级开启外键约束
    """
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


def _foreign_keys_enabled() -> bool:
    """检测当前共享连接的外键强制状态。

    @return: PRAGMA foreign_keys 是否为 ON（1）
    """
    with engine.connect() as conn:
        return bool(conn.exec_driver_sql("PRAGMA foreign_keys").scalar())


@pytest.fixture(scope="module")
def isolated_user_baby():
    """模块级隔离测试用户与宝宝夹具（避免污染演示数据与其他用例的断言）。

    @yield: (user_id, baby_id) 元组
    @raises IntegrityError: 手机号唯一约束冲突时抛出（正常仅创建一次，不应发生）
    """
    with SessionLocal() as db:
        user = User(phone=ISOLATED_PHONE, nickname="约束测试用户", password_hash="not-used")
        db.add(user)
        db.flush()
        baby = Baby(user_id=user.id, name="约束测试宝宝", birth_date=date(2026, 1, 1))
        db.add(baby)
        db.commit()
        yield user.id, baby.id


class TestUniqueConstraints:
    """唯一约束测试组（D07）。"""

    def test_recipe_favorite_unique(self):
        """同一用户重复收藏同一食谱应触发唯一约束 IntegrityError。

        @raises IntegrityError: 插入重复 (user_id, recipe_id) 时由数据库抛出
        """
        with SessionLocal() as db:
            db.add(RecipeFavorite(user_id=1, recipe_id=1))
            db.commit()
            db.add(RecipeFavorite(user_id=1, recipe_id=1))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
            # 清理本用例数据，避免影响其他用例的收藏断言
            db.query(RecipeFavorite).filter_by(user_id=1, recipe_id=1).delete()
            db.commit()

    def test_meal_plan_slot_unique(self, isolated_user_baby):
        """同一宝宝同周同天同餐次（计划槽位）重复插入应触发唯一约束。

        @param isolated_user_baby: 隔离用户与宝宝夹具
        @raises IntegrityError: 插入重复槽位时由数据库抛出
        """
        _, baby_id = isolated_user_baby
        with SessionLocal() as db:
            slot = {
                "baby_id": baby_id,
                "week_start": date(2026, 9, 7),
                "day_of_week": 0,
                "meal_type": "lunch",
                "recipe_id": 1,
            }
            db.add(MealPlan(**slot))
            db.commit()
            db.add(MealPlan(**slot))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
            # 清理本用例计划数据
            db.query(MealPlan).filter_by(
                baby_id=baby_id, week_start=date(2026, 9, 7)
            ).delete()
            db.commit()


class TestCascadeDelete:
    """级联删除测试组（D07）。"""

    def test_delete_user_cascades(self, isolated_user_baby):
        """删除用户后，宝宝档案、饮食记录与收藏应级联删除。

        - User→Baby 与 Baby→DietRecord 均配置 ORM cascade="all, delete-orphan"，
          删除由 ORM 逐层下发 DELETE，不依赖数据库外键开关；
        - RecipeFavorite（用户侧）无 ORM 关系，依赖 ondelete=CASCADE +
          PRAGMA foreign_keys=ON 在数据库层级联；若外键强制未开启则该断言
          按任务约定跳过（跳过原因：SQLite 连接未启用外键，DB 级 CASCADE
          不可验证）。

        @param isolated_user_baby: 隔离用户与宝宝夹具
        @raises AssertionError: 级联删除后仍能查到残留数据时抛出
        """
        user_id, baby_id = isolated_user_baby
        with SessionLocal() as db:
            db.add(
                DietRecord(
                    baby_id=baby_id,
                    record_date=date(2026, 1, 2),
                    record_type="formula",
                    details={"amount_ml": 90},
                )
            )
            db.add(RecipeFavorite(user_id=user_id, recipe_id=1))
            db.commit()

            user = db.get(User, user_id)
            assert user is not None
            db.delete(user)
            db.commit()

            # ORM 级联：宝宝与饮食记录
            assert db.get(Baby, baby_id) is None
            assert db.query(DietRecord).filter_by(baby_id=baby_id).first() is None

            # DB 级级联：收藏（依赖外键强制开启）
            if _foreign_keys_enabled():
                assert db.query(RecipeFavorite).filter_by(user_id=user_id).first() is None
            else:
                pytest.skip(
                    "SQLite 连接外键强制未开启（PRAGMA foreign_keys=OFF），"
                    "DB 级 ondelete=CASCADE 行为无法验证"
                )


class TestMealPlanTransaction:
    """一周计划保存事务保护测试组（D07）。"""

    def test_meal_plan_save_rollback_on_foreign_key_failure(self, client, auth_headers):
        """保存一周计划中途失败（非法 recipe_id 外键冲突）时，旧计划不被误删。

        先保存一份合法计划，再以引用不存在食谱的载荷整体覆盖保存；
        "先删后插"在同一事务内，删除与插入应一起回滚。

        @param client: 测试 HTTP 客户端夹具
        @param auth_headers: 鉴权请求头夹具
        @raises AssertionError: 旧计划被误删或错误码不符合约定时抛出
        """
        if not _foreign_keys_enabled():
            pytest.skip(
                "SQLite 连接外键强制未开启（PRAGMA foreign_keys=OFF），"
                "无法通过非法 recipe_id 构造外键失败场景"
            )
        baby = create_test_baby(client, auth_headers)
        url = f"/api/v1/babies/{baby['id']}/meal-plans"
        week = "2026-08-17"

        # 先保存合法计划
        ok_payload = {
            "week_start": week,
            "items": [{"day_of_week": 0, "meal_type": "lunch", "recipe_id": 1}],
        }
        resp = client.put(url, headers=auth_headers, json=ok_payload)
        assert resp.json()["code"] == 0, resp.text
        assert len(resp.json()["data"]) == 1

        # 破坏性保存：recipe_id 不存在，外键冲突应使整次保存回滚
        bad_payload = {
            "week_start": week,
            "items": [{"day_of_week": 1, "meal_type": "dinner", "recipe_id": 999999}],
        }
        resp = client.put(url, headers=auth_headers, json=bad_payload)
        assert resp.json()["code"] == 50000, resp.text

        # 旧数据未被误删（先删后插整体回滚）
        resp = client.get(url, headers=auth_headers, params={"week_start": week})
        items = resp.json()["data"]
        assert len(items) == 1
        assert items[0]["recipe_id"] == 1
        assert items[0]["day_of_week"] == 0

    def test_meal_plan_duplicate_slot_rejected(self, client, auth_headers):
        """同一载荷内重复槽位应命中唯一约束返回业务错误，且旧数据保留。

        @param client: 测试 HTTP 客户端夹具
        @param auth_headers: 鉴权请求头夹具
        @raises AssertionError: 错误码不符合约定或旧数据丢失时抛出
        """
        baby = create_test_baby(client, auth_headers)
        url = f"/api/v1/babies/{baby['id']}/meal-plans"
        week = "2026-08-24"

        # 先保存合法计划（周一午餐 → 食谱 1）
        resp = client.put(
            url,
            headers=auth_headers,
            json={
                "week_start": week,
                "items": [{"day_of_week": 0, "meal_type": "lunch", "recipe_id": 1}],
            },
        )
        assert resp.json()["code"] == 0, resp.text

        # 同一载荷内两个相同槽位：uq_meal_plans_slot 冲突 → 50000
        resp = client.put(
            url,
            headers=auth_headers,
            json={
                "week_start": week,
                "items": [
                    {"day_of_week": 0, "meal_type": "lunch", "recipe_id": 1},
                    {"day_of_week": 0, "meal_type": "lunch", "recipe_id": 2},
                ],
            },
        )
        assert resp.json()["code"] == 50000, resp.text

        # 旧计划未被误删
        resp = client.get(url, headers=auth_headers, params={"week_start": week})
        items = resp.json()["data"]
        assert len(items) == 1
        assert items[0]["recipe_id"] == 1
