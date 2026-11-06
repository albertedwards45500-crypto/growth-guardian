"""有界候选召回策略。只改变候选池，不授予引用权或放宽资料元数据过滤。"""

from collections import Counter
import math
import re
import unicodedata


STRATEGIES = ("baseline", "expanded", "hybrid")

# 常见虚词及泛化上下文词不能单独证明一份资料回答了问题。
# 这是通用文本归一化，不包含资料标题、评估题或医学答案专用词表。
_LEXICAL_STOP_TERMS = {
    "婴儿", "宝宝", "孩子", "小孩", "辅食", "喂养", "食物", "资料", "准备", "开始",
    "信号", "知识", "问题", "说明", "提到", "指出", "一般", "是否", "需要", "可以",
    "什么", "怎么", "怎样", "哪些", "多少", "如何", "还有", "以及", "关于",
}
_LEXICAL_FUNCTION_CHARS = set("的了是和在要吗还时中给把这那从需能应可及与并或为对到里哪怎么多少有无则将会用应当")


def requires_specific_fact(text):
    """识别需要精确数值/操作事实的问题，避免泛化资料被当作依据。"""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return bool(re.search(
        r"准确|比例|毫升|克|公斤|温度|摄氏|几(?:小时|天|次|个月|岁)|多少(?:毫升|克|度|时间)?|"
        r"多久|多长时间|保存|冷藏|剂量|频率|哪一种|哪类|使用什么|用什么",
        normalized,
    ))


def lexical_terms(text):
    """通用中文二元字组与英文/数字词；不包含试题专用词表或问答规则。"""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = []
    for token in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", normalized):
        if "\u4e00" <= token[0] <= "\u9fff":
            terms.extend(
                term for index in range(len(token) - 1)
                if (term := token[index:index + 2]) not in _LEXICAL_STOP_TERMS
                and not any(char in _LEXICAL_FUNCTION_CHARS for char in term)
            )
        else:
            terms.append(token)
    return Counter(terms)


def lexical_rank(query, candidates):
    """有界TF-IDF余弦排序；字面重合不是相关性或医学可信度。"""
    query_counts = lexical_terms(query)
    documents = [lexical_terms(f"{item['title']}\n{item['text']}") for item in candidates]
    frequencies = Counter(term for document in documents for term in document)
    size = len(documents)
    weights = {term: math.log((size + 1) / (count + 1)) + 1 for term, count in frequencies.items()}

    def weighted(counts):
        return {term: (1 + math.log(count)) * weights.get(term, math.log(size + 1) + 1)
                for term, count in counts.items()}

    query_vector = weighted(query_counts)
    query_norm = math.sqrt(sum(value * value for value in query_vector.values()))
    ranked = []
    for item, terms in zip(candidates, documents):
        vector = weighted(terms)
        dot = sum(value * vector.get(term, 0) for term, value in query_vector.items())
        norm = math.sqrt(sum(value * value for value in vector.values()))
        if dot and norm and query_norm:
            ranked.append((dot / (norm * query_norm), item))
    return [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["id"]))]


def retrieve_candidates(query, dense_search, lexical_loader, *, strategy="baseline", top_k=3,
                        min_score=.55, candidate_top_k=5, candidate_min_score=.45, lexical_scan_limit=200):
    """每条分支必须由调用方使用同一权限/审核/月龄/主题/日期过滤器。"""
    if (strategy not in STRATEGIES or not 1 <= top_k <= 5 or not 1 <= candidate_top_k <= 5
            or (strategy != "baseline" and top_k > candidate_top_k)
            or not math.isfinite(min_score) or not math.isfinite(candidate_min_score)
            or not 0 <= min_score <= 1 or not 0 <= candidate_min_score <= 1
            or not 1 <= lexical_scan_limit <= 1000):
        raise ValueError("候选召回策略参数无效")
    if strategy == "baseline":
        return dense_search(top_k, min_score)
    dense = dense_search(candidate_top_k, min(min_score, candidate_min_score))
    if strategy == "expanded":
        return dense
    lexical = lexical_loader(lexical_scan_limit + 1)
    if len(lexical) > lexical_scan_limit:
        raise ValueError("字面召回超过有界扫描上限，请先建立专用检索索引")
    lexical = lexical_rank(query, lexical)[:candidate_top_k]
    # 对精确事实问题，密集相似度不足以证明资料包含所需数字或操作步骤。
    # 没有实质字面证据时关闭混合候选，交由上层返回“暂无可引用资料”。
    if requires_specific_fact(query) and not lexical:
        return []
    fused, hits, channels = Counter(), {}, {}
    for channel, items in (("dense", dense), ("lexical", lexical)):
        for rank, item in enumerate(items, 1):
            key = item["id"]
            fused[key] += 1 / (60 + rank)
            hits.setdefault(key, item)
            channels.setdefault(key, []).append(channel)
    return [{**hits[key], "retrieval_channels": channels[key], "fusion_score": round(fused[key], 8)}
            for key in sorted(fused, key=lambda key: (-fused[key], key))[:candidate_top_k]]
