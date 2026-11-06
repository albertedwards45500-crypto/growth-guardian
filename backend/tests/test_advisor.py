"""成长顾问契约、数据正确性、权限隔离与安全分流回归测试。"""

from datetime import date
import logging

import pytest
from pydantic import ValidationError

from app.core.database import SessionLocal
from app.core.exceptions import NotFoundError
from app.models.baby import Baby
from app.models.diet import Allergy, DietRecord
from app.models.growth import GrowthRecord
from app.models.recipe import Recipe, MealPlan
from app.models.notification import Notification
from app.schemas.advisor import AdvisorAnswer, AdvisorSource, AdvisorStatement
from app.services.advisor import validate_grounding
from app.services.advisor_safety import allergen_conflict, restricted_request
from app.services.advisor_tools import AdvisorTools
from tests.conftest import create_test_baby

AS_OF = "2026-09-10"


@pytest.fixture()
def baby(client, auth_headers):
    created = create_test_baby(client, auth_headers, name="顾问隐私测试宝宝")
    yield created
    # 会话测试库由所有模块共用；清理本用例档案，避免影响“首个档案为默认”的旧测试。
    with SessionLocal() as db:
        row = db.get(Baby, created["id"])
        if row is not None:
            db.delete(row)
            db.commit()


def ask(client, headers, target_baby_id, question, **kwargs):
    return client.post(
        f"/api/v1/babies/{target_baby_id}/advisor/ask", headers=headers,
        json={"question": question, "as_of": AS_OF, **kwargs},
    )


@pytest.fixture()
def recipe_catalog():
    """只给当前测试使用的目录标签，避免种子食谱数量掩盖过滤回归。"""
    with SessionLocal() as db:
        recipes = [
            Recipe(title="顾问南瓜", suitable_age_min=6, suitable_age_max=36,
                   ingredients=[{"name": "南瓜"}], nutrition_tags=["顾问测试"], steps=[]),
            Recipe(title="顾问蛋黄", suitable_age_min=6, suitable_age_max=36,
                   ingredients=[{"name": "蛋黄"}], nutrition_tags=["顾问测试"], steps=[]),
            Recipe(title="顾问豆腐", suitable_age_min=6, suitable_age_max=36,
                   ingredients=[{"name": "嫩豆腐"}], nutrition_tags=["顾问测试"], steps=[]),
            Recipe(title="顾问复合配料", suitable_age_min=6, suitable_age_max=36,
                   ingredients=[{"name": "复合调味酱"}], nutrition_tags=["顾问测试"], steps=[]),
            Recipe(title="顾问年龄不符", suitable_age_min=12, suitable_age_max=36,
                   ingredients=[{"name": "苹果"}], nutrition_tags=["顾问测试"], steps=[]),
            Recipe(title="顾问已下架", suitable_age_min=6, suitable_age_max=36,
                   ingredients=[{"name": "香蕉"}], nutrition_tags=["顾问测试"], steps=[], is_active=False),
        ]
        db.add_all(recipes)
        db.commit()
        ids = [item.id for item in recipes]
    yield ids
    with SessionLocal() as db:
        db.query(Recipe).filter(Recipe.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


def test_auth_and_baby_ownership(client, auth_headers, demo_headers, baby):
    path = f"/api/v1/babies/{baby['id']}/advisor/ask"
    assert client.post(path, json={"question": "成长回顾"}).json()["code"] == 40100
    assert ask(client, demo_headers, baby["id"], "宝宝呼吸困难").json()["code"] == 40400
    with SessionLocal() as db:
        owner = db.get(Baby, baby["id"])
        wrong_user = db.query(Baby).filter(Baby.user_id != owner.user_id).first()
        assert wrong_user is not None
        with pytest.raises(NotFoundError):
            AdvisorTools(db, wrong_user.user_id, baby["id"], date.fromisoformat(AS_OF))


@pytest.mark.parametrize("override", [
    {"user_id": 1}, {"baby_id": 1}, {"exclude_allergens": False}, {"actions": [{"type": "delete"}]},
    {"question": "   "}, {"as_of": "2099-01-01"}, {"as_of": "2025-01-01"},
    {"days": 0}, {"days": 32}, {"intent": "delete_records"},
])
def test_request_cannot_override_trust_boundary(client, auth_headers, baby, override):
    response = ask(client, auth_headers, baby["id"], "成长回顾", **override) if "question" not in override else ask(
        client, auth_headers, baby["id"], override["question"],
    )
    assert response.json()["code"] == 42200


def test_no_data_is_not_healthy_or_zero_intake(client, auth_headers, baby):
    growth = ask(client, auth_headers, baby["id"], "成长回顾").json()["data"]
    assert growth["generation_mode"] == "rules"
    assert growth["tool_statuses"][0]["status"] == "no_data"
    assert growth["safety_level"] == "caution"
    assert growth["missing_information"] and not growth["observations"]
    diet = ask(client, auth_headers, baby["id"], "总结最近一周吃了什么").json()["data"]
    assert diet["intent"] == "diet_review"
    assert diet["tool_statuses"][0]["status"] == "no_data"
    assert not diet["observations"]


def test_growth_independent_metrics_dates_and_snapshot(client, auth_headers, baby):
    with SessionLocal() as db:
        db.add_all([
            GrowthRecord(baby_id=baby["id"], record_date=date(2026, 8, 1), weight_kg=7),
            GrowthRecord(baby_id=baby["id"], record_date=date(2026, 9, 1), weight_kg=7.5),
            GrowthRecord(baby_id=baby["id"], record_date=date(2026, 9, 1), weight_kg=7.6),
            GrowthRecord(baby_id=baby["id"], record_date=date(2026, 9, 2), height_cm=69),
            GrowthRecord(baby_id=baby["id"], record_date=date(2026, 9, 11), weight_kg=8),
        ])
        db.commit()
    response = ask(client, auth_headers, baby["id"], "回顾身高和体重").json()["data"]
    text = " ".join(item["text"] for item in response["observations"])
    assert "7.6 kg" in text and "+0.6 kg" in text and "69 cm" in text
    assert "2026-09-11" not in text and "8 kg" not in text
    assert all(source["as_of"] <= AS_OF for source in response["sources"])
    assert all(source["type"] != "who_reference" for source in response["sources"])
    assert "user_id" not in str(response) and baby["name"] not in str(response)


def test_diet_aggregates_only_window_and_valid_details(client, auth_headers, baby):
    with SessionLocal() as db:
        db.add_all([
            DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 4), record_type="formula", details={"amount_ml": 120}),
            DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 10), record_type="formula", details={"amount_ml": "坏数据"}),
            DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 10), record_type="formula", details={"amount_ml": -100}),
            DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 10), record_type="breast_milk", details={"left_minutes": 10, "right_minutes": 5}),
            DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 10), record_type="solid_food", details={"food_items": ["南瓜", "苹果"]}),
            DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 3), record_type="formula", details={"amount_ml": 900}),
            DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 11), record_type="formula", details={"amount_ml": 900}),
        ])
        db.commit()
    response = ask(client, auth_headers, baby["id"], "总结一周饮食").json()["data"]
    text = " ".join(item["text"] for item in response["observations"])
    assert "5条" in text and "120 ml" in text and "15分钟" in text
    assert "南瓜" in text and "900" not in text
    assert any("明细无效" in risk for risk in response["risks"])
    assert any("未记录不等于" in item for item in response["missing_information"])


def test_bad_milk_details_do_not_generate_zero_intake(client, auth_headers, baby):
    with SessionLocal() as db:
        db.add(DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 10), record_type="formula", details=None))
        db.commit()
    response = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    assert not any("0 ml" in item["text"] for item in response["observations"])
    assert any("明细无效" in risk for risk in response["risks"])


def test_extreme_numeric_details_fail_closed(client, auth_headers, baby):
    with SessionLocal() as db:
        db.add(DietRecord(baby_id=baby["id"], record_date=date(2026, 9, 10), record_type="formula",
                          details={"amount_ml": 10 ** 400}))
        db.commit()
    result = ask(client, auth_headers, baby["id"], "饮食回顾").json()
    assert result["code"] == 0
    assert not any("ml" in item["text"] for item in result["data"]["observations"])


def test_recipe_filters_aliases_composites_age_and_inactive(client, auth_headers, baby, recipe_catalog):
    with SessionLocal() as db:
        db.add_all([Allergy(baby_id=baby["id"], ingredient="鸡蛋", severity="severe"),
                    Allergy(baby_id=baby["id"], ingredient="大豆")])
        db.commit()
    result = ask(client, auth_headers, baby["id"], "根据过敏史推荐辅食", nutrition="顾问测试").json()["data"]
    assert [item["title"] for item in result["recipe_candidates"]] == ["顾问南瓜"]
    assert result["safety_level"] == "caution"  # 既往严重程度不等于当前急症。
    assert not result["actions"]
    sources = {item["id"] for item in result["sources"]}
    assert all(set(item["evidence_ids"]) <= sources for item in result["recipe_candidates"])


def test_missing_allergy_history_is_explicit(client, auth_headers, baby, recipe_catalog):
    data = ask(client, auth_headers, baby["id"], "推荐辅食", nutrition="顾问测试").json()["data"]
    assert data["recipe_candidates"]
    assert data["safety_level"] == "caution"
    assert any("不能推断没有过敏" in item for item in data["missing_information"])


def test_invalid_allergy_list_blocks_candidates(client, auth_headers, baby, recipe_catalog):
    with SessionLocal() as db:
        db.add(Allergy(baby_id=baby["id"], ingredient="   "))
        db.commit()
    data = ask(client, auth_headers, baby["id"], "推荐辅食", nutrition="顾问测试").json()["data"]
    assert not data["recipe_candidates"]
    assert any(item["status"] == "invalid" for item in data["tool_statuses"])


@pytest.mark.parametrize("question,level", [
    ("宝宝呼吸困难，推荐辅食", "emergency"), ("宝宝现在叫不醒", "emergency"),
    ("宝宝没有呼吸了", "emergency"), ("baby has blue lips", "emergency"),
    ("无糖酸奶吃后嘴唇发紫", "emergency"),
    ("宝宝持续呕吐，看看饮食", "urgent"), ("如果宝宝呼吸困难怎么办", "caution"),
    ("宝宝没有呼吸困难", "caution"), ("宝宝没有明显的呼吸困难", "caution"),
    ("没有呼吸困难但嘴唇发紫", "emergency"),
])
def test_risk_precedes_intent_and_tools(client, auth_headers, baby, monkeypatch, question, level):
    def forbidden(*args, **kwargs):
        raise AssertionError("高风险分流不得继续读取业务记录")
    monkeypatch.setattr(AdvisorTools, "get_growth_summary", forbidden)
    monkeypatch.setattr(AdvisorTools, "recommend_safe_recipes", forbidden)
    monkeypatch.setattr(AdvisorTools, "get_diet_summary", forbidden)
    data = ask(client, auth_headers, baby["id"], question, intent="recipe_recommendation").json()["data"]
    assert data["safety_level"] == level
    assert not data["tool_statuses"] and not data["recipe_candidates"]
    assert not data["actions"] and data["intent"] == "clarification_needed"


@pytest.mark.parametrize("question", [
    "删除宝宝成长记录", "给宝宝生成一周餐单", "宝宝该吃多少布洛芬", "宝宝是不是缺铁",
    "宝宝对鸡蛋过敏，推荐辅食", "鸡蛋过敏了吃什么", "今天天气怎样",
])
def test_restricted_or_unsupported_requests(client, auth_headers, baby, question):
    data = ask(client, auth_headers, baby["id"], question).json()["data"]
    assert data["intent"] == "clarification_needed"
    assert not data["actions"] and not data["recipe_candidates"]


@pytest.mark.parametrize("food,allergen", [
    ("蛋黄", "鸡蛋"), ("无糖酸奶", "牛奶"), ("嫩豆腐", "大豆"),
    ("核桃油", "坚果"), ("鲜虾", "海鲜"), ("小麦面粉", "小麦"), ("egg yolk", "鸡蛋"),
])
def test_allergen_family_exclusion(food, allergen):
    assert allergen_conflict(food, allergen)
    assert not allergen_conflict("南瓜", allergen)


@pytest.mark.parametrize(("question", "restricted"), [
    ("保存宝宝成长记录", True),
    ("修改宝宝档案", True),
    ("做好的辅食放在冷藏室最多可以保存几小时？", False),
    ("辅食在冰箱里保存多久比较合适？", False),
])
def test_restricted_request_distinguishes_writes_from_food_storage(question, restricted):
    assert restricted_request(question) is restricted


def test_unverified_knowledge_and_reference_not_medical_sources(client, auth_headers, baby):
    with SessionLocal() as db:
        owner = db.get(Baby, baby["id"])
        tools = AdvisorTools(db, owner.user_id, owner.id, date.fromisoformat(AS_OF))
        assert tools.search_feeding_guides().data["review_status"] == "unverified"
        assert tools.search_feeding_faqs("过敏").status == "partial"
        assert tools.search_feeding_faqs("%").status == "no_data"
        assert tools.get_growth_curve().data is None
        assert tools.get_milestones().status == "no_data"
        profile = tools.get_baby_profile().data
        assert set(profile) == {"age_months", "age_days", "gender"}


def test_output_contract_rejects_fabricated_sources_and_writes(client, auth_headers, baby):
    with pytest.raises(ValidationError):
        AdvisorAnswer(request_id="test", as_of=date(2026, 9, 10), intent="growth_review",
                      safety_level="normal", summary="test",
                      observations=[AdvisorStatement(text="虚构事实", evidence_ids=["growth_record:fake"])])
    with pytest.raises(ValidationError):
        AdvisorAnswer(request_id="test", as_of=date(2026, 9, 10), intent="growth_review",
                      safety_level="normal", summary="test", actions=[{"type": "delete"}])
    with SessionLocal() as db:
        owner = db.get(Baby, baby["id"])
        tools = AdvisorTools(db, owner.user_id, owner.id, date.fromisoformat(AS_OF))
        fake = AdvisorSource(id="fake:1", type="guide", label="伪造指南")
        answer = AdvisorAnswer(request_id="test", as_of=tools.as_of, intent="growth_review",
                               safety_level="normal", summary="test", sources=[fake])
        with pytest.raises(ValueError, match="本次工具结果"):
            validate_grounding(answer, tools)


def test_queries_read_only_and_audit_does_not_log_question(client, auth_headers, baby, caplog):
    models = (GrowthRecord, DietRecord, Allergy, MealPlan, Notification)
    with SessionLocal() as db:
        before = [db.query(model).count() for model in models]
    with caplog.at_level(logging.INFO, logger="baby_growth.advisor"):
        question = "顾问隐私测试宝宝成长记录回顾"
        data = ask(client, auth_headers, baby["id"], question).json()["data"]
    audit = " ".join(record.getMessage() for record in caplog.records if record.name == "baby_growth.advisor")
    assert data["request_id"] in audit
    assert question not in audit and baby["name"] not in audit
    with SessionLocal() as db:
        assert before == [db.query(model).count() for model in models]


def test_output_validation_failure_returns_fixed_fallback(client, auth_headers, baby, monkeypatch):
    def reject(*args):
        raise ValueError("不应暴露的内部内容")
    monkeypatch.setattr("app.services.advisor.validate_grounding", reject)
    response = ask(client, auth_headers, baby["id"], "成长回顾").json()
    assert response["code"] == 0
    assert "未通过数据校验" in response["data"]["summary"]
    assert "内部内容" not in str(response)
    assert not response["data"]["sources"] and not response["data"]["actions"]


def test_tampered_candidate_ingredients_rejected(client, auth_headers, baby, recipe_catalog):
    response = ask(client, auth_headers, baby["id"], "推荐辅食", nutrition="顾问测试").json()["data"]
    answer = AdvisorAnswer.model_validate(response)
    answer.recipe_candidates[0].ingredients.append("未经筛选的花生")
    with SessionLocal() as db:
        owner = db.get(Baby, baby["id"])
        tools = AdvisorTools(db, owner.user_id, owner.id, date.fromisoformat(AS_OF))
        tools.get_baby_profile()
        tools.recommend_safe_recipes("顾问测试")
        with pytest.raises(ValueError, match="被修改"):
            validate_grounding(answer, tools)
