"""权限绑定的只读工具。每个实例对应一次请求，不接受模型提供的身份或 SQL。"""

from datetime import date, timedelta
import math

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_baby_or_404
from app.core.config import settings
from app.core.exceptions import BusinessError
from app.models.advice import Faq
from app.models.diet import Allergy, DietRecord
from app.models.growth import GrowthRecord, Milestone
from app.schemas.advisor import AdvisorSource, AdvisorToolResult, advisor_today
from app.services.advice import match_guide
from app.services.advisor_safety import allergen_conflict, recipe_ingredients
from app.services.growth import compute_age
from app.services.recipe import recommend_recipes


def source(kind: str, record_id: int, label: str, on: date | None = None) -> AdvisorSource:
    """构建可追溯来源，不返回记录备注等无关自由文本。"""
    return AdvisorSource(id=f"{kind}:{record_id}", type=kind, label=label, as_of=on)


class AdvisorTools:
    """工具身份由已认证路由传入；所有宝宝记录查询固定使用已校验的档案。"""

    def __init__(self, db: Session, user_id: int, baby_id: int, as_of: date):
        self.db = db
        self.baby = get_baby_or_404(baby_id, db, user_id)
        if as_of > advisor_today() or as_of < self.baby.birth_date:
            raise BusinessError(42200, "查询日期应在宝宝出生日期与今天之间")
        self.as_of = as_of
        self.results: list[AdvisorToolResult] = []

    def _result(self, tool: str, status: str, data=None, evidence=None, warnings=None, missing=None):
        result = AdvisorToolResult(
            tool=tool, status=status, baby_id=self.baby.id, data=data,
            evidence=evidence or [], warnings=warnings or [], missing=missing or [],
        )
        self.results.append(result)
        return result

    def get_baby_profile(self) -> AdvisorToolResult:
        """仅提供本次分析需要的月龄和性别，省略姓名、照片和出生日期。"""
        months, days = compute_age(self.baby.birth_date, self.as_of)
        warnings = ["月龄按当前档案出生日期计算，档案没有历史版本。"] if self.as_of != advisor_today() else []
        return self._result("get_baby_profile", "partial" if warnings else "ok", {
            "age_months": months, "age_days": days, "gender": self.baby.gender,
        }, [source("baby_profile", self.baby.id, "宝宝月龄档案", self.as_of)], warnings)

    def _growth_rows(self):
        start = max(self.baby.birth_date, self.as_of - timedelta(days=89))
        rows = self.db.query(GrowthRecord).filter(
            GrowthRecord.baby_id == self.baby.id,
            GrowthRecord.record_date.between(start, self.as_of),
        ).order_by(GrowthRecord.record_date.desc(), GrowthRecord.id.desc()).limit(181).all()
        warnings = ["近90天记录超过180条，仅使用最近180条。"] if len(rows) > 180 else []
        points, evidence = [], []
        invalid = False
        for row in rows[:180]:
            point = {"record_date": row.record_date.isoformat(), "id": row.id}
            for field, maximum in (("weight_kg", 50), ("height_cm", 150), ("head_circumference_cm", 100)):
                value = getattr(row, field)
                if value is not None:
                    if math.isfinite(value) and 0 < value <= maximum:
                        point[field] = value
                    else:
                        invalid = True
            if len(point) > 2:
                points.append(point)
                evidence.append(source("growth_record", row.id, f"{row.record_date} 测量记录", row.record_date))
        if invalid:
            warnings.append("已忽略超出数据录入范围的测量值，请核实原记录。")
        return start, points, evidence, warnings

    def get_growth_summary(self) -> AdvisorToolResult:
        """各指标独立取最新值，只比较两个不同日期的测量，不推断健康状态。"""
        start, points, evidence, warnings = self._growth_rows()
        if not points:
            return self._result("get_growth_summary", "invalid" if warnings else "no_data",
                                warnings=warnings, missing=["近90天有效身高、体重或头围记录"])
        metrics, missing = {}, []
        for field in ("weight_kg", "height_cm", "head_circumference_cm"):
            values, dates = [], set()
            for point in points:
                if field in point and point["record_date"] not in dates:
                    values.append(point)
                    dates.add(point["record_date"])
            if not values:
                missing.append(f"{field}测量记录")
                continue
            latest = values[0]
            metric = {"value": latest[field], "date": latest["record_date"], "evidence_ids": [f"growth_record:{latest['id']}"]}
            if len(values) > 1:
                previous = values[1]
                metric["comparison"] = {
                    "previous_date": previous["record_date"],
                    "delta": round(latest[field] - previous[field], 3),
                    "evidence_ids": [f"growth_record:{previous['id']}", f"growth_record:{latest['id']}"],
                }
            else:
                missing.append(f"{field}另一日期的测量记录（用于比较）")
            metrics[field] = metric
        if any((self.as_of - date.fromisoformat(metric["date"])).days > 30 for metric in metrics.values()):
            warnings.append("部分测量记录距查询日超过30天，无法代表当前状况。")
        return self._result("get_growth_summary", "partial" if missing or warnings else "ok", {
            "period_start": start.isoformat(), "period_end": self.as_of.isoformat(), "metrics": metrics,
        }, evidence, warnings, missing)

    def get_growth_curve(self) -> AdvisorToolResult:
        """提供有界测量点；现有近似WHO绘图数据不进入健康评估工具。"""
        start, points, evidence, warnings = self._growth_rows()
        return self._result("get_growth_curve", "partial" if points else "no_data", {
            "period_start": start.isoformat(), "period_end": self.as_of.isoformat(),
            "points": list(reversed(points)), "clinical_reference": None,
        } if points else None, evidence,
            warnings + ["现有WHO数据为绘图近似值，本工具不计算临床分位或诊断。"],
            ["经验证的正式生长参考数据"])

    def get_milestones(self) -> AdvisorToolResult:
        """只汇总已记录的里程碑，不把未填写解释为发育落后。"""
        rows = self.db.query(Milestone).filter(
            Milestone.baby_id == self.baby.id,
            Milestone.achieved_at.between(self.baby.birth_date, self.as_of),
        ).order_by(Milestone.achieved_at.desc(), Milestone.id.desc()).limit(51).all()
        return self._result("get_milestones", "partial" if len(rows) > 50 else "ok" if rows else "no_data", {
            "items": [{"type": row.milestone_type, "date": row.achieved_at.isoformat()} for row in rows[:50]],
        }, [source("milestone", row.id, f"{row.achieved_at} 里程碑记录", row.achieved_at) for row in rows[:50]],
            ["未记录不代表未达成；不评估发育是否落后。"] + (["仅返回最近50条。"] if len(rows) > 50 else []))

    def get_diet_summary(self, days: int = 7) -> AdvisorToolResult:
        """有界聚合实际录入量；缺失/损坏明细不能被解释为零摄入。"""
        if not 1 <= days <= 31:
            raise ValueError("饮食回顾天数必须在1至31之间")
        start = max(self.baby.birth_date, self.as_of - timedelta(days=days - 1))
        rows = self.db.query(DietRecord).filter(
            DietRecord.baby_id == self.baby.id, DietRecord.record_date.between(start, self.as_of),
        ).order_by(DietRecord.record_date.desc(), DietRecord.id.desc()).limit(501).all()
        if not rows:
            return self._result("get_diet_summary", "no_data", missing=[f"{start}至{self.as_of}的饮食记录"])
        warnings = ["窗口内记录超过500条，仅统计最近500条。"] if len(rows) > 500 else []
        counts = {"breast_milk": 0, "formula": 0, "solid_food": 0}
        formula_ml, breast_minutes, food_names, dates, evidence = 0, 0, set(), set(), []
        formula_valid, breast_valid = False, False
        invalid = False
        for row in rows[:500]:
            dates.add(row.record_date)
            evidence.append(source("diet_record", row.id, f"{row.record_date} 饮食记录", row.record_date))
            details = row.details if isinstance(row.details, dict) else {}
            if row.record_type not in counts:
                invalid = True
                continue
            counts[row.record_type] += 1
            if row.record_type == "solid_food":
                items = details.get("food_items")
                if isinstance(items, list) and 0 < len(items) <= 100 and all(
                    isinstance(item, str) and item.strip() and len(item) <= 80 for item in items
                ):
                    food_names.update(item.strip() for item in items)
                else:
                    invalid = True
                continue
            keys = ("amount_ml",) if row.record_type == "formula" else ("left_minutes", "right_minutes")
            if not any(key in details for key in keys):
                invalid = True
            for key in keys:
                if key not in details:
                    continue
                value = details[key]
                # 不把字符串、布尔、负数或NaN强制转换为有效摄入量。
                if type(value) not in (int, float) or not 0 <= value <= 1000000 or not math.isfinite(value):
                    invalid = True
                elif key == "amount_ml":
                    formula_ml += value
                    formula_valid = True
                else:
                    breast_minutes += value
                    breast_valid = True
        missing = ["完整进食量和食物营养成分（无法判断营养是否达标）"]
        if len(dates) < (self.as_of - start).days + 1:
            missing.append("部分日期未记录，未记录不等于没有进食")
        if invalid:
            warnings.append("部分饮食明细无效或缺失，数值只累计可验证的已录入部分。")
        if len(food_names) > 100:
            warnings.append("食材种类超过100项，仅列出排序前100项。")
        return self._result("get_diet_summary", "partial", {
            "period_start": start.isoformat(), "period_end": self.as_of.isoformat(),
            "record_count": len(rows[:500]), "recorded_days": len(dates), "counts": counts,
            "formula_ml_recorded": formula_ml if formula_valid else None,
            "breast_minutes_recorded": breast_minutes if breast_valid else None,
            "food_names": sorted(food_names)[:100],
        }, evidence, warnings, missing)

    def get_allergies(self) -> AdvisorToolResult:
        """始终采用当前全部过敏记录保护推荐，不将无记录判为不过敏。"""
        rows = self.db.query(Allergy).filter(Allergy.baby_id == self.baby.id).order_by(Allergy.id).limit(101).all()
        warnings = []
        if self.as_of != advisor_today():
            warnings.append("过敏清单没有历史版本，使用当前清单而非查询日的历史状态。")
        if len(rows) > 100 or any(not row.ingredient or not row.ingredient.strip() for row in rows):
            return self._result("get_allergies", "invalid", warnings=warnings + ["过敏清单过长或含无效名称，暂停食谱推荐。"])
        return self._result("get_allergies", "ok" if rows else "no_data", {
            "items": [{"ingredient": row.ingredient.strip(), "severity": row.severity} for row in rows],
        }, [source("allergy", row.id, "当前已记录过敏食材", advisor_today()) for row in rows], warnings,
            [] if rows else ["过敏史尚未记录，不能推断没有过敏"])

    def recommend_safe_recipes(self, nutrition: str | None = None) -> AdvisorToolResult:
        """复用现有适龄SQL筛选，再做同类过敏排除及复合配料核验；最多5项。"""
        allergies = self.get_allergies()
        if allergies.status == "invalid":
            return self._result("recommend_safe_recipes", "invalid", warnings=allergies.warnings)
        age = compute_age(self.baby.birth_date, self.as_of)[0]
        if age < 6 or age > 36:
            return self._result("recommend_safe_recipes", "no_data", missing=["当前工具仅支持6至36月龄的辅食候选筛选"])
        rows = recommend_recipes(self.db, self.baby, age_months=age, nutrition=nutrition, limit=201)
        allergens = [item["ingredient"] for item in allergies.data["items"]]
        items, evidence, excluded_unknown = [], [], 0
        for row in rows[:200]:
            names = recipe_ingredients(row.ingredients)
            tags = row.nutrition_tags or []
            if names is None or not row.title.strip() or not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                excluded_unknown += 1
                continue
            if any(allergen_conflict(name, allergen) for name in names for allergen in allergens):
                continue
            items.append({"recipe_id": row.id, "title": row.title, "ingredients": names,
                          "nutrition_tags": tags})
            evidence.append(source("recipe", row.id, f"食谱目录：{row.title}", advisor_today()))
            if len(items) == 5:
                break
        warnings = ["候选仅依据目录食材、月龄和已记录过敏史筛选，不保证个体耐受或不存在交叉污染。",
                    "目录营养标签未经营养成分核算，不能据此判断补充效果。"]
        if excluded_unknown:
            warnings.append("已排除配料不完整或复合成分不明确的食谱。")
        if len(rows) > 200:
            warnings.append("仅筛选目录中前200条适龄候选。")
        return self._result("recommend_safe_recipes", "partial" if items else "no_data", {
            "items": items, "age_months": age,
        }, evidence, warnings, [] if items else ["当前条件下可核验食材的适龄食谱"])

    def search_reviewed_knowledge(self, query: str, topic: str) -> AdvisorToolResult:
        """身份/月龄/日期由后端固定；仅检索审核公共资料，不使用演示指南。"""
        if not settings.RAG_ENABLED:
            return self._result("search_reviewed_knowledge", "no_data", missing=["RAG检索未启用"])
        if topic not in ("growth_review", "diet_review", "recipe_recommendation", "feeding_knowledge"):
            raise ValueError("不支持的知识主题")
        if not settings.RAG_EMBEDDING_API_KEY.get_secret_value():
            return self._result("search_reviewed_knowledge", "no_data", missing=["Embedding服务尚未配置"])
        allergies = next((item for item in self.results if item.tool == "get_allergies"), None)
        allergies = allergies or self.get_allergies()
        if allergies.status == "invalid":
            return self._result("search_reviewed_knowledge", "invalid",
                                warnings=["过敏清单无法核实，本次暂停知识摘录。"])
        try:
            from app.services.knowledge import get_knowledge_store

            hits = get_knowledge_store().search(
                query, compute_age(self.baby.birth_date, self.as_of)[0], topic, self.as_of,
                top_k=settings.RAG_TOP_K, min_score=settings.RAG_MIN_SCORE,
            )
        except Exception:
            # 网络/索引异常可能带密钥、正文或服务地址，不回显异常对象。
            return self._result("search_reviewed_knowledge", "invalid",
                                warnings=["知识检索暂不可用，本次仅整理可验证的记录。"])
        # 对摘录也做保守排除，包括正文里的别名；不尝试理解“可吃/忌吃”等句意。
        # 因而可能连有益的避敏说明一起排除，但不会把相似度当成个体耐受依据。
        allergens = [item["ingredient"] for item in allergies.data["items"]]
        filtered = [hit for hit in hits if not any(
            allergen_conflict(hit["text"], allergen) for allergen in allergens
        )]
        excluded = len(filtered) != len(hits)
        hits = filtered
        warnings = ["知识摘录为公共教育资料，不能据此判断个体诊断、剂量或食材耐受。"] if hits else []
        if excluded:
            warnings.append("已保守排除提及已登记过敏食材及常见同类名称的知识段落。")
        return self._result("search_reviewed_knowledge", "partial" if hits else "no_data", {"items": hits}, [
            AdvisorSource(id=hit["id"], type="reviewed_knowledge", label=hit["title"],
                          url=hit["url"], version=hit["version"], reviewed_on=date.fromisoformat(hit["reviewed_on"]))
            for hit in hits
        ], warnings,
            [] if hits else ["适合本次问题、月龄和日期的已审核知识"])

    def search_feeding_guides(self) -> AdvisorToolResult:
        """演示知识库缺少审核/文献元数据，明确标记为未验证，不能用于诊疗生成。"""
        guide = match_guide(self.db, compute_age(self.baby.birth_date, self.as_of)[0])
        return self._result("search_feeding_guides", "partial" if guide else "no_data", {
            "title": guide.title, "content": guide.content, "review_status": "unverified",
        } if guide else None,
            [source("unverified_guide", guide.id, "站内演示指南（未经医学审核）")] if guide else [],
            ["指南缺少可追溯文献和审核信息，不用于生成医学结论或个体摄入量。"], ["经审核且含版本信息的指南"])

    def search_feeding_faqs(self, keyword: str, category: str | None = None) -> AdvisorToolResult:
        """关键词按字面检索，最多5项；检索内容只能作为未审核资料。"""
        if not keyword.strip() or len(keyword) > 50:
            raise ValueError("FAQ关键词须为1至50字")
        query = self.db.query(Faq).filter(or_(
            Faq.question.contains(keyword, autoescape=True), Faq.keywords.contains(keyword, autoescape=True),
        ))
        if category:
            query = query.filter(Faq.category == category)
        rows = query.order_by(Faq.id).limit(5).all()
        return self._result("search_feeding_faqs", "partial" if rows else "no_data", {
            "items": [{"question": row.question, "answer": row.answer} for row in rows], "review_status": "unverified",
        }, [source("unverified_faq", row.id, "站内FAQ（未经医学审核）") for row in rows],
            ["FAQ未经医学审核，不能把检索到的诊断、再挑战或用药内容直接作为建议。"], ["经审核的知识来源"])
