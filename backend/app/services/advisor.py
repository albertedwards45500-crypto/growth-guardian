"""只读成长顾问：代码控制安全和事实，可配置 LangGraph 与审核知识检索。"""

import logging
import re
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.advisor import (
    AdvisorAnswer, AdvisorAskRequest, AdvisorRecipeCandidate, AdvisorRecommendation,
    AdvisorStatement, AdvisorToolStatus, advisor_today,
)
from app.services.advisor_safety import restricted_request, triage_question
from app.services.advisor_tools import AdvisorTools

logger = logging.getLogger("baby_growth.advisor")


def mentions_specific_allergy(question: str) -> bool:
    return bool(re.search(r"对.{1,20}过敏|[鸡鸭鹅牛羊鱼虾蟹蛋奶豆麦花生坚果芝麻][^，。！？]{0,5}过敏", question))


def classify_intent(payload: AdvisorAskRequest) -> str:
    """小范围意图识别；无法识别的问题返回支持范围，而不猜测用户需求。"""
    if payload.intent:
        return payload.intent
    question = payload.question
    if any(word in question for word in ("食谱", "推荐辅食", "推荐食物", "吃什么", "辅食推荐", "辅食搭配")):
        return "recipe_recommendation"
    if any(word in question for word in ("饮食", "喂养", "奶量", "吃了", "吃过", "进食")):
        return "diet_review"
    if any(word in question for word in ("成长", "生长", "身高", "身长", "体重", "头围")):
        return "growth_review"
    if any(word in question for word in ("辅食", "喂养知识", "添加食物")):
        return "feeding_knowledge"
    return "clarification_needed"


def validate_grounding(answer: AdvisorAnswer, tools: AdvisorTools) -> AdvisorAnswer:
    """用实际工具结果校验引用与候选，不允许自行构造来源或新增食材。"""
    answer = AdvisorAnswer.model_validate(answer.model_dump())
    expected_sources = {item.id: item for result in tools.results for item in result.evidence}
    if any(expected_sources.get(item.id) != item for item in answer.sources):
        raise ValueError("回答来源与本次工具结果不一致")
    candidates = {
        item["recipe_id"]: item
        for result in tools.results if result.tool == "recommend_safe_recipes" and result.data
        for item in result.data["items"]
    }
    for candidate in answer.recipe_candidates:
        expected = candidates.get(candidate.recipe_id)
        if expected is None or any(
            getattr(candidate, field) != expected[field]
            for field in ("title", "ingredients", "nutrition_tags")
        ):
            raise ValueError("食谱候选未经本次工具核验或被修改")
        if f"recipe:{candidate.recipe_id}" not in candidate.evidence_ids:
            raise ValueError("食谱缺少对应的目录依据")
    if answer.safety_level in ("urgent", "emergency") and answer.recipe_candidates:
        raise ValueError("紧急分流不得继续食谱推荐")
    knowledge = {
        item["id"]: item["text"] for result in tools.results
        if result.tool == "search_reviewed_knowledge" and result.data
        for item in result.data["items"]
    }
    if any(knowledge.get(quote.evidence_id) != quote.text for quote in answer.knowledge):
        raise ValueError("知识摘录与本次检索原文不一致")
    if answer.safety_level in ("urgent", "emergency") and answer.knowledge:
        raise ValueError("紧急分流不得继续知识检索")
    return answer


def _growth_answer(answer: AdvisorAnswer, tools: AdvisorTools) -> None:
    result = tools.get_growth_summary()
    if result.data is None:
        answer.summary = "查询范围内没有足够的有效测量记录，暂时无法回顾成长变化。"
        answer.safety_level = "caution"
    else:
        answer.summary = "以下按近90天已录入的测量记录整理，仅比较数值变化。"
        for field, label, unit in (("weight_kg", "体重", "kg"), ("height_cm", "身高/身长", "cm"),
                                   ("head_circumference_cm", "头围", "cm")):
            metric = result.data["metrics"].get(field)
            if metric is None:
                continue
            answer.observations.append(AdvisorStatement(
                text=f"{metric['date']}记录{label}{metric['value']:g} {unit}。",
                evidence_ids=metric["evidence_ids"],
            ))
            comparison = metric.get("comparison")
            if comparison:
                delta = comparison["delta"]
                answer.observations.append(AdvisorStatement(
                    text=f"与{comparison['previous_date']}的上一日期记录相比，{label}差值为{delta:+g} {unit}。",
                    evidence_ids=comparison["evidence_ids"],
                ))
                if delta < 0:
                    answer.risks.append(f"{label}记录出现下降，请先核实单位和测量条件；持续变化可联系儿科医生评估。")
                    answer.safety_level = "caution"
    answer.recommendations.append(AdvisorRecommendation(
        text="请在相近条件下记录测量日期、单位和数值，便于后续比较。", type="monitoring",
    ))


def _diet_answer(answer: AdvisorAnswer, tools: AdvisorTools, days: int) -> None:
    result = tools.get_diet_summary(days)
    if result.data is None:
        answer.summary = "所选时间范围没有饮食记录，不能据此推断实际进食情况。"
        return
    data = result.data
    evidence_ids = [item.id for item in result.evidence]
    answer.summary = f"已整理{data['period_start']}至{data['period_end']}的饮食记录。"
    answer.observations.append(AdvisorStatement(
        text=f"共有{data['record_count']}条记录，涉及{data['recorded_days']}个日期；其中辅食记录{data['counts']['solid_food']}条。",
        evidence_ids=evidence_ids,
    ))
    if data["counts"]["formula"] and data["formula_ml_recorded"] is not None:
        answer.observations.append(AdvisorStatement(
            text=f"可验证的已录入配方奶量合计{data['formula_ml_recorded']:g} ml，不代表完整实际摄入。", evidence_ids=evidence_ids,
        ))
    if data["counts"]["breast_milk"] and data["breast_minutes_recorded"] is not None:
        answer.observations.append(AdvisorStatement(
            text=f"已录入母乳喂养时长合计{data['breast_minutes_recorded']:g}分钟；时长不能换算为奶量。", evidence_ids=evidence_ids,
        ))
    if data["food_names"]:
        answer.observations.append(AdvisorStatement(
            text="已记录辅食食材：" + "、".join(data["food_names"]) + "。", evidence_ids=evidence_ids,
        ))
    answer.recommendations.append(AdvisorRecommendation(
        text="继续记录实际喂养和宝宝反应；完整进食量和食物成分不足时，无法评估营养是否达标。", type="monitoring",
    ))


def _recipe_answer(answer: AdvisorAnswer, tools: AdvisorTools, payload: AdvisorAskRequest) -> None:
    # 自然语言中的新过敏信息无法可靠结构化时，暂停推荐，避免只按旧清单筛选。
    if mentions_specific_allergy(payload.question):
        answer.intent = "clarification_needed"
        answer.safety_level = "caution"
        answer.summary = "问题提到了具体食材过敏，请先核实并更新宝宝的过敏清单，再筛选辅食。"
        answer.missing_information.append("已核实并记录的完整过敏史")
        return
    tools.get_baby_profile()
    result = tools.recommend_safe_recipes(payload.nutrition)
    if result.data is None or not result.data["items"]:
        answer.summary = "当前条件下没有可提供的适龄食谱候选，请核实过敏信息和配料。"
        return
    allergy_result = next(item for item in tools.results if item.tool == "get_allergies")
    context_ids = [item.id for item in tools.results[0].evidence] + [item.id for item in allergy_result.evidence]
    answer.summary = "以下为按档案月龄和当前已记录过敏史筛选的食谱候选，食用前仍需核对实际配料。"
    for item in result.data["items"]:
        answer.recipe_candidates.append(AdvisorRecipeCandidate(
            **item, evidence_ids=[f"recipe:{item['recipe_id']}", *context_ids],
        ))
    if allergy_result.data["items"]:
        answer.observations.append(AdvisorStatement(
            text="已按当前登记的过敏食材及常见同类名称执行排除。",
            evidence_ids=[item.id for item in allergy_result.evidence],
        ))
    answer.recommendations.append(AdvisorRecommendation(
        text="核对完整包装配料及交叉接触情况；未吃过的食材不能据此认定已经耐受。", type="monitoring",
    ))


def ask_advisor(db: Session, user_id: int, baby_id: int, payload: AdvisorAskRequest) -> AdvisorAnswer:
    """认证上下文绑定后先分流，再按意图最小化读取；记录脱敏运行元数据。"""
    tools = AdvisorTools(db, user_id, baby_id, payload.as_of or advisor_today())
    answer = AdvisorAnswer(
        request_id=f"req_{uuid4().hex}", as_of=tools.as_of, intent=classify_intent(payload),
        safety_level="normal", summary="请说明需要回顾成长记录、饮食记录，还是筛选辅食食谱。",
    )
    triage = triage_question(payload.question)
    if triage:
        answer.safety_level = triage
        answer.intent = "clarification_needed"
        if triage == "emergency":
            answer.summary = "描述中包含可能需要立即急救的情况；若正在发生，请立即拨打120或当地急救电话。"
            answer.recommendations = [AdvisorRecommendation(
                text="立即寻求急救帮助并遵循急救调度人员指导，不要等待在线建议。", type="seek_care", priority="high",
            )]
        elif triage == "urgent":
            answer.summary = "描述中包含需要尽快由医护人员评估的情况，请及时联系儿科或急诊。"
            answer.recommendations = [AdvisorRecommendation(
                text="若伴有呼吸异常、叫不醒或迅速恶化，请立即寻求急救帮助。", type="seek_care", priority="high",
            )]
        else:
            answer.summary = "请先确认这些紧急症状是否正在发生；若正在发生，请立即拨打120或当地急救电话。"
        answer.risks = ["文字规则仅能识别部分风险，不能完成医学分诊或判断宝宝安全。"]
    elif restricted_request(payload.question):
        answer.intent = "clarification_needed"
        answer.safety_level = "caution"
        answer.summary = "成长顾问支持只读记录回顾和食谱候选筛选；诊疗或用药请咨询儿科医生，记录变更请使用对应管理页面。"
    elif answer.intent == "growth_review":
        _growth_answer(answer, tools)
    elif answer.intent == "diet_review":
        _diet_answer(answer, tools, payload.days)
    elif answer.intent == "recipe_recommendation":
        _recipe_answer(answer, tools, payload)
    elif answer.intent == "feeding_knowledge":
        answer.safety_level = "caution"
        answer.summary = "知识问答需要启用智能体并配置已审核知识库；当前暂不能提供可引用的相关资料。"
        if mentions_specific_allergy(payload.question):
            answer.intent = "clarification_needed"
            answer.summary = "问题提到了具体食材过敏，请先核实并更新宝宝的过敏清单，再查阅适用的喂养资料。"
            answer.missing_information.append("已核实并记录的完整过敏史")

    if settings.ADVISOR_AGENT_ENABLED:
        if answer.intent == "clarification_needed":
            answer.agent_status = "skipped_safety"
        elif not settings.OPENAI_API_KEY.get_secret_value() or not settings.ADVISOR_MODEL.strip():
            answer.agent_status = "unavailable"
            answer.missing_information.append("智能体模型或服务密钥尚未配置，本次使用规则回答")
        else:
            try:
                from app.services.advisor_agent import run_agent

                answer = run_agent(tools, payload, answer.model_copy(deep=True))
            except Exception:
                logger.warning("advisor_agent_failed request_id=%s", answer.request_id)
                answer.agent_status = "failed"
                answer.risks.append("智能体暂不可用，本次返回规则整理结果。")

    answer.sources = list({item.id: item for result in tools.results for item in result.evidence}.values())
    answer.tool_statuses = [AdvisorToolStatus(
        tool=result.tool, status=result.status, warnings=result.warnings, missing=result.missing,
    ) for result in tools.results]
    answer.risks = list(dict.fromkeys(answer.risks + [warning for result in tools.results for warning in result.warnings]))
    answer.missing_information = list(dict.fromkeys(
        answer.missing_information + [missing for result in tools.results for missing in result.missing]
    ))
    if answer.safety_level == "normal" and any(result.status != "ok" for result in tools.results):
        answer.safety_level = "caution"
    try:
        answer = validate_grounding(answer, tools)
    except (ValueError, ValidationError):
        # 不回显未通过校验的内容，也不把内部异常/工具原始值暴露给用户。
        logger.error("advisor_output_rejected request_id=%s", answer.request_id)
        answer = AdvisorAnswer(
            request_id=answer.request_id, as_of=tools.as_of, intent="clarification_needed",
            safety_level="caution", summary="本次内容未通过数据校验，请稍后重试或查看原始记录。",
        )
    logger.info("advisor_completed request_id=%s intent=%s safety_level=%s agent_status=%s tools=%s",
                answer.request_id, answer.intent, answer.safety_level, answer.agent_status,
                ",".join(f"{result.tool}:{result.status}" for result in tools.results))
    return answer
