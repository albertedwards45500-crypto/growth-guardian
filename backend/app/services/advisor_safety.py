"""成长顾问的保守分流与食材匹配规则；不构成医学诊断或完整分诊系统。"""

import re
import unicodedata


def normalize_food(value: str) -> str:
    """统一食材名称，匹配按字面执行，不把 %、_ 当作查询通配符。"""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


# 保守的常见过敏源同类映射，仅用于排除；不用于判断能否耐受。
ALLERGEN_GROUPS = (
    ("鸡蛋", "鸭蛋", "鹌鹑蛋", "蛋黄", "蛋白", "蛋清", "鸡蛋白", "egg", "albumin"),
    ("牛奶", "牛乳", "奶", "乳制品", "奶粉", "配方奶", "奶酪", "酸奶", "乳酪", "乳清", "乳粉", "乳蛋白", "酪蛋白", "milk", "cheese", "yogurt", "casein"),
    ("大豆", "黄豆", "豆腐", "豆浆", "豆奶", "酱油", "soy", "tofu"),
    ("小麦", "面粉", "面条", "馄饨皮", "饺子皮", "麸质", "wheat", "gluten"),
    ("花生", "peanut"),
    ("坚果", "核桃", "腰果", "杏仁", "榛子", "开心果", "碧根果", "巴旦木", "nut", "almond", "walnut", "cashew"),
    ("鱼", "fish", "cod", "salmon", "tuna"),
    ("虾", "蟹", "龙虾", "shrimp", "prawn", "crab", "lobster"),
    ("贝", "蛤蜊", "牡蛎", "贻贝", "蚝", "mussel", "clam", "oyster", "scallop"),
    ("芝麻", "sesame"),
)


def allergen_conflict(ingredient: str, allergen: str) -> bool:
    """字面命中或同类命中即排除，无法据此保证无交叉污染或未知过敏。"""
    food, allergy = normalize_food(ingredient), normalize_food(allergen)
    for suffix in ("过敏", "制品", "类"):
        allergy = allergy.removesuffix(suffix)
    if not food or not allergy:
        return True
    if allergy in food or food in allergy:
        return True
    if "海鲜" in allergy or "shellfish" in allergy:
        return any(term in food for group in ALLERGEN_GROUPS[6:9] for term in group)
    return any(
        any(term in allergy for term in group) and any(term in food for term in group)
        for group in ALLERGEN_GROUPS
    )


COMPOSITE_FOODS = (
    "米粉", "面条", "馄饨皮", "饺子皮", "面粉", "淀粉", "奶酪", "酸奶", "调味", "酱",
    "高汤", "肉丸", "饼干", "香肠", "混合", "复合", "预拌", "cereal", "pasta", "flour",
    "yogurt", "cheese", "formula",
)


def recipe_ingredients(raw: object) -> list[str] | None:
    """无法确认的复合配料或损坏的食材清单整份排除，最多解析两层配料。"""
    def parse(items: object, depth: int) -> list[str] | None:
        if not isinstance(items, list) or not items or depth > 2:
            return None
        names: list[str] = []
        for item in items:
            name = item.get("name") if isinstance(item, dict) else item
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                return None
            food = normalize_food(name)
            if any(term in food for term in ("未知", "不详", "其他", "unknown")):
                return None
            components = item.get("components") if isinstance(item, dict) else None
            if components is not None:
                nested = parse(components, depth + 1)
                if nested is None:
                    return None
                names.extend(nested)
            elif any(term in food for term in COMPOSITE_FOODS):
                return None
            names.append(name.strip())
        return list(dict.fromkeys(names))

    return parse(raw, 0)


def triage_question(question: str) -> str | None:
    """识别有限的紧急表述，否定/假设句仍提示确认，不据此宣布安全。"""
    text = unicodedata.normalize("NFKC", question).casefold()
    terms = (
        "呼吸困难", "不能呼吸", "没有呼吸", "停止呼吸", "喘不上气", "喘不过气", "嘴唇发紫",
        "嘴唇青紫", "叫不醒", "昏迷", "失去意识", "意识不清", "过敏性休克", "抽搐",
        "cannot breathe", "can't breathe", "trouble breathing", "difficulty breathing",
        "blue lips", "unresponsive", "unconscious",
    )
    uncertain = False
    for term in terms:
        for match in re.finditer(re.escape(term), text):
            if term == "没有呼吸" and re.match(r"困难|异常|问题", text[match.end():]):
                continue
            prefix = re.split(r"[，。！？；,.;!?]|但是|但|却", text[:match.start()])[-1][-14:]
            negated = re.search(
                r"(?:没有|并无|并未|无|未出现|没出现|不是|no\s|not\s)\s*(?:(?:出现过|出现|发生|明显|任何|的)\s*)*$",
                prefix,
            )
            hypothetical = re.search(r"如果|假如|万一|预防|避免|\bif\s", prefix)
            if negated or hypothetical:
                uncertain = True
            else:
                return "emergency"
    if uncertain:
        return "caution"
    if any(term in text for term in ("持续呕吐", "反复呕吐", "明显脱水", "严重脱水", "便血", "尿量明显减少")):
        return "urgent"
    return None


def restricted_request(question: str) -> bool:
    """只读记录顾问不接受诊疗、用药或记录写入请求。"""
    return bool(re.search(
        r"诊断|是不是.{0,8}(病|过敏|缺铁|缺锌)|是否.{0,8}(病|过敏)|吃什么药|用药|药量|剂量|停药|退烧药|布洛芬|阿莫西林|"
        r"删除|(?:修改|创建|新增).{0,12}(宝宝|记录|档案|数据|资料|食谱|计划|提醒)|"
        r"保存.{0,12}(宝宝|记录|档案|数据|资料|食谱|计划|提醒)|"
        r"添加.{0,6}记录|生成.{0,6}(餐单|计划)|安排.{0,6}(餐单|提醒)",
        question,
    ))
