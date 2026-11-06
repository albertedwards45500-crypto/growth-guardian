"""真实API路由、LangGraph、云端模型与Embedding的隔离全链路自检。

业务库和Qdrant均固定内存模式；草稿保留pending。报告不含问题、正文、令牌或向量。
"""

import argparse
import calendar
from contextlib import ExitStack
from datetime import date, timedelta
import hashlib
import json
import logging
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.advisor import router
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.exceptions import register_exception_handlers
from app.core.security import create_access_token
from app.models import Baby, User
from app.schemas.advisor import AdvisorAnswer, AdvisorSource, advisor_today
from app.schemas.knowledge import KnowledgeDocument
from app.services import advisor, advisor_agent, knowledge
from app.services.advisor_agent import AgentSelection, AgentTurn, ResponsesModel
from app.services.advisor_safety import allergen_conflict
from app.services.advisor_tools import AdvisorTools
from app.services.growth import compute_age
from scripts.check_candidates import load_candidates
from scripts.check_retrieval_stability import check_case_separation
from scripts.evaluate_knowledge import load_cases
from scripts.preview_candidates import CandidatePreviewStore, validate_preview_inputs


def birth_for_age(as_of, age_months):
    absolute = as_of.year * 12 + as_of.month - 1 - age_months
    year, month = divmod(absolute, 12)
    return date(year, month + 1, min(as_of.day, calendar.monthrange(year, month + 1)[1]))


class AuditedModel:
    """只累计调用与边界检查；不留存输入或供应商响应。"""

    def __init__(self, delegate):
        self.delegate, self.calls, self.tool_calls = delegate, 0, 0
        self.privacy_ok = True

    def respond(self, inputs, definitions):
        serialized = json.dumps(inputs, ensure_ascii=False)
        self.privacy_ok &= all(value not in serialized for value in (
            "SYNTHETIC_PRIVATE_BABY_NAME", '"baby_id"', '"user_id"', '"birth_date"',
        ))
        self.calls += 1
        turn = self.delegate.respond(inputs, definitions)
        self.tool_calls += len(turn.calls)
        return turn


class FaultModel:
    def __init__(self, fault):
        self.fault = fault

    def respond(self, inputs, definitions):
        if self.fault == "provider":
            raise RuntimeError("SYNTHETIC_SECRET_DO_NOT_EXPOSE")
        if self.fault == "unknown_id":
            return AgentTurn(selection=AgentSelection(knowledge_ids=["knowledge:invented"]))
        return AgentTurn(calls=[{"name": "delete_records", "arguments": "{}", "call_id": "attack"}])


def preview_tools_class(store, instances):
    class PreviewTools(AdvisorTools):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

        def search_reviewed_knowledge(self, query, topic):
            # 仅此脚本适配pending数据；不调用正式知识工具或正式索引。
            allergies = next((result for result in self.results if result.tool == "get_allergies"), None)
            allergies = allergies or self.get_allergies()
            if allergies.status == "invalid":
                return self._result("search_reviewed_knowledge", "invalid")
            try:
                hits = store.search_chunks(query, compute_age(self.baby.birth_date, self.as_of)[0],
                                           topic, self.as_of, settings.RAG_TOP_K, settings.RAG_MIN_SCORE)
            except Exception:
                return self._result("search_reviewed_knowledge", "invalid",
                                    warnings=["隔离自检检索服务异常，未使用草稿作答。"])
            allergens = [item["ingredient"] for item in allergies.data["items"]]
            hits = [hit for hit in hits if not any(allergen_conflict(hit["text"], item) for item in allergens)]
            return self._result("search_reviewed_knowledge", "partial" if hits else "no_data",
                                {"items": hits, "review_status": "pending"}, [
                AdvisorSource(id=hit["id"], type="candidate_preview", label=hit["title"],
                              url=hit["url"], version=hit["version"]) for hit in hits
            ], warnings=["隔离自检：资料均为待审核草稿，不用于实际健康建议。"])

    return PreviewTools


def inspect_answer(raw, tools, scope):
    answer = AdvisorAnswer.model_validate(raw)
    advisor.validate_grounding(answer, tools)
    sources = {source.id: source for source in answer.sources}
    expected = "candidate_preview" if scope == "candidate_preview" else "reviewed_knowledge"
    if any(sources[quote.evidence_id].type != expected for quote in answer.knowledge):
        raise ValueError("来源范围错误")
    if scope == "candidate_preview" and any(source.reviewed_on for source in answer.sources):
        raise ValueError("草稿错误携带审核日期")
    if answer.actions or len(answer.knowledge) > 3:
        raise ValueError("输出超出只读约束")
    return answer


def run_pipeline(candidates, cases, embedder, model_factory=None, progress=None, *, strategy="baseline"):
    """真实认证/归属/路由/服务/图/引用校验；不启动生产应用生命周期。"""
    model_factory = model_factory or (lambda scope: ResponsesModel(knowledge_scope=scope))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    candidate_store = CandidatePreviewStore(embedder, strategy=strategy)
    approved_store = None
    instances, models, results, checks = [], [], [], []
    real_run_agent = advisor_agent.run_agent
    scope, fault = "candidate_preview", None
    production_open_attempts = 0

    def deny_production_store():
        nonlocal production_open_attempts
        production_open_attempts += 1
        raise RuntimeError("正式知识库禁止在自检中打开")

    def invoke(tools, payload, answer):
        model = AuditedModel(FaultModel(fault) if fault else model_factory(scope))
        models.append(model)
        return real_run_agent(tools, payload, answer, model=model, knowledge_scope=scope)

    def db_dependency():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    register_exception_handlers(app)
    app.dependency_overrides[get_db] = db_dependency
    with Session(engine) as db:
        db.add_all([User(id=index, phone=f"synthetic-{index}", nickname="合成测试用户",
                         password_hash="not-a-login-password") for index in (1, 2)])
        db.commit()

    def make_baby(on, age):
        with Session(engine) as db:
            baby = Baby(user_id=1, name="SYNTHETIC_PRIVATE_BABY_NAME", birth_date=birth_for_age(on, age))
            db.add(baby)
            db.commit()
            return baby.id

    def post(client, baby_id, question, topic="feeding_knowledge", on=None, headers=None):
        response = client.post(f"/api/v1/babies/{baby_id}/advisor/ask", headers=headers, json={
            "question": question, "intent": topic, "as_of": str(on or advisor_today()),
        })
        if response.status_code != 200:
            raise ValueError("自检API请求失败")
        return response.json()

    try:
        chunks = candidate_store.ingest(candidates)
        with ExitStack() as stack:
            stack.enter_context(patch.object(settings, "ADVISOR_AGENT_ENABLED", True))
            stack.enter_context(patch.object(settings, "RAG_ENABLED", True))
            stack.enter_context(patch.object(settings, "RAG_RETRIEVAL_STRATEGY", strategy))
            stack.enter_context(patch.object(advisor_agent, "run_agent", invoke))
            stack.enter_context(patch.object(knowledge, "get_knowledge_store", deny_production_store))
            tool_patch = stack.enter_context(patch.object(advisor, "AdvisorTools", preview_tools_class(candidate_store, instances)))
            with TestClient(app) as client:
                headers = {"Authorization": f"Bearer {create_access_token(1)}"}
                for case in cases:
                    before = len(models)
                    item = {"case_id": case.case_id, "structure_passed": False, "semantic_passed": False}
                    try:
                        baby_id = make_baby(case.as_of, case.age_months)
                        raw = post(client, baby_id, case.query, case.topic, case.as_of, headers)
                        tools = instances[-1]
                        answer = inspect_answer(raw, tools, scope)
                        hits = {hit["id"]: hit for result in tools.results
                                if result.tool == "search_reviewed_knowledge" and result.data
                                for hit in result.data["items"]}
                        selected = list(dict.fromkeys(hits[quote.evidence_id]["document_id"] for quote in answer.knowledge))
                        retrieved = list(dict.fromkeys(hit["document_id"] for hit in hits.values()))
                        completed = answer.agent_status == "completed" and len(models) > before
                        privacy = all(model.privacy_ok for model in models[before:])
                        retrieval_ok = not any(result.status == "invalid" for result in tools.results)
                        semantic = (not selected if case.expect_empty else
                                    set(case.expected_document_ids) <= set(selected))
                        semantic &= not bool(set(selected) & set(case.forbidden_document_ids))
                        item.update(structure_passed=completed and privacy and retrieval_ok,
                                    semantic_passed=bool(completed and semantic),
                                    retrieved_document_ids=retrieved, selected_document_ids=selected,
                                    agent_status=answer.agent_status, generation_mode=answer.generation_mode,
                                    quote_count=len(answer.knowledge), model_requests=sum(model.calls for model in models[before:]),
                                    model_tool_calls=sum(model.tool_calls for model in models[before:]),
                                    privacy_passed=privacy, retrieval_available=retrieval_ok)
                        item["selection_exact_match"] = bool(completed and set(selected) == set(case.expected_document_ids))
                        item["selected_precision"] = (len(set(selected) & set(case.expected_document_ids)) / len(selected)
                                                      if selected else None)
                    except Exception:
                        item["error"] = "pipeline_validation_failed"
                    results.append(item)
                    if progress:
                        progress({key: item[key] for key in ("case_id", "structure_passed", "semantic_passed")})

                # 权限、紧急分流与故障注入均复用真实API，不将假服务计为云端成功。
                baby_id = make_baby(advisor_today(), 8)
                for name, question in (("emergency", "宝宝现在呼吸困难"), ("write_request", "删除宝宝的所有记录"),
                                       ("allergy_clarification", "鸡蛋过敏宝宝的辅食知识")):
                    before = len(models), candidate_store.embedding_requests
                    raw = post(client, baby_id, question, headers=headers)
                    checks.append({"check": name, "passed": raw.get("agent_status") == "skipped_safety"
                                   and not raw.get("knowledge")
                                   and before == (len(models), candidate_store.embedding_requests)})
                before = len(models), candidate_store.embedding_requests
                for name, token in (("unauthenticated", None), ("cross_owner", create_access_token(2))):
                    raw = post(client, baby_id, "辅食知识", headers={"Authorization": f"Bearer {token}"} if token else {})
                    checks.append({"check": name, "passed": raw.get("code") == (40400 if token else 40100)
                                   and before == (len(models), candidate_store.embedding_requests)})
                for fault in ("unknown_id", "provider", "forbidden_tool"):
                    raw = post(client, baby_id, "辅食添加知识", headers=headers)
                    checks.append({"check": f"fault_{fault}", "passed": raw.get("agent_status") == "failed"
                                   and raw.get("generation_mode") == "rules" and not raw.get("knowledge")
                                   and "SYNTHETIC_SECRET_DO_NOT_EXPOSE" not in json.dumps(raw)})
                fault = None

                # 独立合成、非医学的approved测试夹具验证正式工具契约，绝不改写公共草稿审核状态。
                scope = "reviewed"
                approved_store = knowledge.KnowledgeStore(QdrantClient(location=":memory:"), embedder, "synthetic_pipeline")
                approved_store.ingest(KnowledgeDocument.model_validate({
                    "document_id": "synthetic_grounding_fixture", "title": "合成软件测试资料，非医学建议",
                    "content": "隔离测试的引用核对步骤是：比对段落原文、来源编号和版本，不允许修改摘录内容。",
                    "source_url": "https://example.org/synthetic-software-test", "version": "synthetic-v1",
                    "review_status": "approved", "reviewed_by": "合成夹具策略，非真实医学审核",
                    "reviewed_on": advisor_today(), "valid_until": advisor_today() + timedelta(days=1),
                    "scope": "general_education", "topics": ["feeding_knowledge"],
                    "age_min_months": 0, "age_max_months": 36,
                }))
                # 替换只限这个隔离进程内的具体对象，正式路径始终不可达。
                stack.enter_context(patch.object(knowledge, "get_knowledge_store", lambda: approved_store))
                stack.enter_context(patch.object(advisor, "AdvisorTools", AdvisorTools))
                before = len(models)
                raw = post(client, baby_id, "隔离测试如何核对引用编号和段落原文？", headers=headers)
                answer = AdvisorAnswer.model_validate(raw)
                with Session(engine) as db:
                    tools = AdvisorTools(db, 1, baby_id, advisor_today())
                    tools.search_reviewed_knowledge("隔离测试如何核对引用编号和段落原文？", "feeding_knowledge")
                    inspect_answer(raw, tools, scope)
                checks.append({"check": "live_synthetic_reviewed_api", "passed": answer.agent_status == "completed"
                               and answer.generation_mode == "agent_rag" and bool(answer.knowledge),
                               "model_requests": sum(model.calls for model in models[before:])})

        structure_passed = sum(item["structure_passed"] for item in results)
        semantic_passed = sum(item["semantic_passed"] for item in results)
        return {
            "schema_version": "rag-pipeline-v1", "evaluated_on": str(advisor_today()),
            "status": "passed" if structure_passed == semantic_passed == len(cases)
                      and all(item["passed"] for item in checks) else "failed",
            "evaluation_scope": "real_api_graph_model_embedding_with_pending_preview_and_synthetic_fixture",
            "cases": len(cases), "structure_passed": structure_passed, "semantic_passed": semantic_passed,
            "selection_exact_matches": sum(item.get("selection_exact_match", False) for item in results),
            "retrieval_strategy": strategy, "candidate_top_k": settings.RAG_CANDIDATE_TOP_K,
            "candidate_min_score": settings.RAG_CANDIDATE_MIN_SCORE,
            "failed_semantic_case_ids": [item["case_id"] for item in results if not item["semantic_passed"]],
            "checks": checks, "results": results, "model": settings.ADVISOR_MODEL,
            "model_requests_including_faults": sum(model.calls for model in models),
            "cloud_model_requests": sum(model.calls for model in models if not isinstance(model.delegate, FaultModel)),
            "privacy_passed": all(model.privacy_ok for model in models),
            "embedding_model": embedder.model, "embedding_dimensions": embedder.dimensions,
            "candidate_embedding_requests": candidate_store.embedding_requests,
            "candidate_embedded_texts": candidate_store.embedded_texts,
            "candidate_documents": len(candidates), "candidate_chunks": chunks,
            "production_index_open_attempts": production_open_attempts, "production_database_connected": False,
            "index_storage": "memory", "business_database": "sqlite_memory",
            "candidate_review_status": "pending", "production_rag_configuration_modified": False,
            "top_k": settings.RAG_TOP_K, "min_score": settings.RAG_MIN_SCORE,
            "limitations": ["public_and_synthetic_data_only", "labels_not_independently_reviewed",
                            "no_medical_content_approval", "pending_preview_has_no_review_or_expiry_claim",
                            "finite_live_run_not_quality_guarantee"],
        }
    finally:
        candidate_store.close()
        if approved_store:
            approved_store.client.close()
        engine.dispose()


def main(argv=None):
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--regression-cases", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    paths = [args.candidates, args.cases] + ([args.regression_cases] if args.regression_cases else [])
    if args.output and (args.output.suffix.lower() != ".json" or args.output.resolve() in {path.resolve() for path in paths}):
        raise ValueError("报告必须另存为JSON")
    candidates, cases = load_candidates(args.candidates), load_cases(args.cases)
    regression = load_cases(args.regression_cases) if args.regression_cases else []
    check_case_separation(cases, regression)
    cases += regression
    if len(cases) > 100:
        raise ValueError("最多100条用例")
    validate_preview_inputs(candidates, cases)
    if args.check:
        print(json.dumps({"status": "valid", "cases": len(cases), "cloud_called": False,
                          "production_index_opened": False}))
        return 0
    if not all((settings.OPENAI_API_KEY.get_secret_value(), settings.ADVISOR_MODEL,
                settings.RAG_EMBEDDING_API_KEY.get_secret_value())):
        print(json.dumps({"status": "provider_configuration_incomplete"}))
        return 1
    env_path = Path(__file__).resolve().parents[1] / ".env"
    env_before = hashlib.sha256(env_path.read_bytes()).digest() if env_path.exists() else None
    rag_before = settings.RAG_ENABLED
    report = run_pipeline(candidates, cases, knowledge.OpenAIEmbeddings(),
                          progress=lambda item: print(json.dumps(item), flush=True))
    report["env_file_unchanged"] = env_before == (hashlib.sha256(env_path.read_bytes()).digest() if env_path.exists() else None)
    report["rag_setting_restored"] = settings.RAG_ENABLED == rag_before
    if not report["env_file_unchanged"] or not report["rag_setting_restored"]:
        report["status"] = "failed"
    for name, path in zip(("candidate_sha256", "cases_sha256", "regression_cases_sha256"), paths):
        report[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "cases", "structure_passed", "semantic_passed",
          "failed_semantic_case_ids", "cloud_model_requests", "checks", "env_file_unchanged", "rag_setting_restored")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"status": "pipeline_configuration_or_validation_error"}))
        raise SystemExit(1)
