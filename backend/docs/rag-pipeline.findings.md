# RAG完整链路自检

日期：2026-10-23。真实调用 `deepseek-flash`、`BAAI/bge-m3`（1024维）和内存Qdrant。

结论：完整技术链路已经跑通，**质量验收尚未全部通过**。47题结构检查47/47通过，依据现有草稿标签的最终文献选择45/47通过；不是47题全部正确，也不代表可提供医疗建议。机器报告的 `status` 因此保留 `failed`。

## 实际执行范围

执行真实HTTP路由、JWT认证、宝宝归属校验、风险分流、后端月龄/主题/日期过滤、云端Embedding、Qdrant召回、LangGraph模型选择/工具循环、原文与来源校验和 `AdvisorAnswer` 结构化响应。未使用前端页面或生产部署代理，不将此称为生产全栈验收。

- 公共草稿5份、原回归17题、挑战30题。输入文件哈希写入 `rag-pipeline.report.json`，没有修改草稿、标签或0.55阈值。
- 公共资料始终为 `pending`，只在进程内的预览适配器提供。来源类型为 `candidate_preview`，没有伪造审核日期，模型指令及摘要明确说明待审核、隔离测试，不展示为正式审核知识。
- 应用原 `search_reviewed_knowledge` 正式工具另用一份明确标注“合成软件测试、非医学建议”的测试夹具跑真实云端API，验证正式工具和引用契约。夹具的测试审核字段不是对WHO/NHS资料的真实医学内容批准。
- 51次真实模型请求，其中3个公共问题触发额外一轮许可工具调用。另有3次假模型故障注入，不计入真实云端成功。
- 待审核预览部分49次Embedding请求、53段输入；此计数不包含独立合成夹具的Embedding。
- SQLite业务库和两个Qdrant集合均为固定内存模式。没有读取真实宝宝库、打开正式向量集合或修改 `.env`；进程内开关退出后恢复。报告不含问题、正文、密钥、令牌或原始向量。

## 结果

| 层级 | 结果 | 解释 |
| --- | --- | --- |
| 结构、原文和来源 | 47/47通过 | 每题完成模型处理；引用匹配本次段落及来源，结构通过校验，无写操作 |
| 最终文献选择 | 45/47通过 | 按现有期望/禁止文献标签检查，不是专家独立评估或医学准确率 |
| 权限、安全与降级 | 9/9通过 | 紧急问题、写请求、过敏澄清、无认证、跨用户；未知引用、供应商异常、越权工具；正式工具合成夹具 |
| 数据隔离 | 通过 | 模型输入检查未见宝宝姓名、身份/出生日期字段；正式索引打开次数为0，环境文件未变 |

本次实际执行了3次许可工具调用，说明不只是固定的“检索后直接生成”单轮请求。

### 已避免的3个误召回

此前纯检索误召回的 `challenge-first-tooth`、`challenge-daily-milk-volume` 和 `unsupported-topic-content`，本次仍有向量候选，但真实模型均选择空列表。最终返回资料不足，不将长牙、牙刷护理、具体奶量问题错误地引用为通用辅食/蜂蜜资料。

这说明“有相似向量候选”不等于“最终一定引用”，也不能保证模型今后始终会拒绝所有无关候选。

### 仍未通过的2个问题

| case_id | 现象 | 所处阶段 |
| --- | --- | --- |
| `challenge-turn-away` | 闭嘴、转头的变体问法没有召回饱足信号资料 | 召回前置阈值 |
| `challenge-eye-hand-mouth` | 眼、手、口配合的问法没有召回辅食准备资料 | 召回前置阈值 |

两题在本次0.55阈值下均无候选；模型没有资料可选，最终安全返回缺少资料。此前稳定性诊断中相关资料得分约0.52039和0.49226，仅用于定位问题，不能当作本次重新记录的相似度。当前证据不支持归因于引用校验故障或模型编造。

未通过降低阈值、增加试题专用关键词、修改期望标签或伪造审核信息获取全通过。本次任务是跑完整链路并自检；召回调优应作为独立变更，保留这些失败例，并新增未参与调优的验证问题评估误召回/漏召回权衡。

## 重现

从 `backend` 目录执行。`--check` 完全离线；真实运行会把公开问题、草稿和合成夹具发送给本地配置的模型/Embedding服务，产生API用量，须先确认文件公开且同意服务商处理。

```powershell
.\.venv\Scripts\python.exe scripts/check_rag_pipeline.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --check
.\.venv\Scripts\python.exe scripts/check_rag_pipeline.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --output docs/rag-pipeline.report.json
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

退出码0仅表示本次所有检查均通过，1包括质量未通过或配置/服务异常。先看结构结果、安全检查和逐例内容，不把退出码1一概当作模型服务不可用。即使某次47题全通过，内容审核、有效期、地区适用性和独立验证仍然是正式启用前的独立门槛。正式RAG继续关闭。
