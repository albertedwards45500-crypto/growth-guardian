# 召回优化实施状态

日期：2026-10-26（保留2026-10-23的实施背景）。

## 已实施

- 新增共享候选召回策略模块，正式审核知识工具和待审核预览适配器复用同一策略。
- 保留默认baseline（TopK=3、最低余弦0.55）；可在隔离实验选择expanded（候选TopK=5、0.45）和hybrid（同一向量候选 + 有界字面排序/RRF融合）。这不是自动采用新策略的上线变更。
- 正式检索两条分支复用审核、主题、月龄、查询日和当前有效期过滤。原文/来源校验、过敏排除、权限检查和只读限制未取消。
- 字面扫描最多200段，超限失败关闭；候选相似度与融合排名分开，纯字面候选没有伪造余弦分数。
- 新增24条合成验证题（12正例、12无资料/边界例）。先比较原47题，再冻结策略并检查新题；新题不参与选择。合成标签不等于专家审核。
- 新增完整比较脚本，跨策略仅在进程内复用相同文本向量，不存问题或向量到正式集合；最多260次模型请求，耗尽预算后阻止新的云端请求。

本轮选择流程、固定参数及评估限制见 [固定协议](retrieval-optimization.protocol.md)。

## 2026-10-26真实比较结果

在用户授权范围内，使用DeepSeek模型和硅基流动 `BAAI/bge-m3`，仅发送公开问题、公开pending草稿和非医学合成夹具。完整报告为 `docs/retrieval-comparison.report.json`，结果为 `quality_failed`：

- 开发集47题：baseline 45/47，expanded 47/47，hybrid 47/47；hybrid精确选择39题，高于expanded的38题，因此按预先固定协议选择hybrid。
- 新增验证集24题：baseline 23/24，失败为葡萄切分漏召回；hybrid 23/24，葡萄漏召回修复，但“婴儿粥米水准确比例”无资料题误引用WHO资料。
- `holdout-fridge-hours`已恢复正常：此前被`保存`写入规则误判为安全分流，现已收窄为只拦截带宝宝/记录/档案/数据等写入对象的表达；该题现在正常完成且保持无引用。
- 结构检查24/24、安全检查9/9通过；云端模型请求210次、Embedding请求75次。`.env`未变化，运行设置已恢复，未打开正式索引，资料仍为`pending`。

因此不能把hybrid作为已验收的生产策略，也不能把这批结果当作医学内容审核。正式RAG继续关闭；下一步应先人工审核资料与无资料题误引用原因，再设计独立的精确率门槛和回归集。

## 已知误引用的离线修复

对 `holdout-porridge-ratio` 的旧报告进行原因分析：混合召回将低证据密集候选与有字面支持的候选一起交给模型。泛化上下文词不足以证明资料包含问题所求的准确比例；模型选择WHO段落后，服务端虽然保留了原文校验，却无法判断该原文是否回答了比例问题。

共享混合召回现已加入通用保守门控：先在字面索引中忽略泛化上下文词和常见功能字；对比例、数量、温度、时长、次数等精确事实问题，如果没有剩余的实质字面重合，就不给模型任何候选。这样会优先造成无资料/暂不引用，而不是让泛化相似度冒充直接证据。它是通用检索规则，不含本题、文献或医学答案专用词表；baseline和expanded策略不变，候选门控也不代表资料已审核。

新离线测试确认：精确比例题面对当前公开草稿集合返回空候选；葡萄切分等含实质实体重合的召回回归继续通过。全套测试为368项通过，包含1条已有AnyIO弃用警告和1条pytest缓存权限警告。当前执行环境阻止外网套接字，本轮未重新调用云端模型或Embedding。原 `retrieval-comparison.report.json` 保持不变并仍为 `quality_failed`；旧验证集已消耗，不能把对已知失败题的修复测试当作独立质量验收。正式RAG继续关闭，公共草稿仍为 `pending`。生产采用前仍需人工审核资料，并用新编制、独立标注的精确率与无资料题集进行隔离复验。

此前比较报告不包含密钥或真实宝宝数据；输入哈希、原始问题和正文不写入报告。

## 复现命令

在 `backend` 目录运行。第一条完全离线，第二条是本轮尚未启动的云端比较命令，需要执行环境允许对应网络请求。

```powershell
.\.venv\Scripts\python.exe scripts/compare_retrieval.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --holdout-cases docs/knowledge-evaluation.holdout.json --check
.\.venv\Scripts\python.exe scripts/compare_retrieval.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --holdout-cases docs/knowledge-evaluation.holdout.json --output docs/retrieval-comparison.report.json
```

新报告文件与原始 `rag-pipeline.report.json` 分开，避免覆盖上一轮真实结果。即使比较通过，也不改`.env`或自动启用RAG；公共草稿仍待真实内容审核。
