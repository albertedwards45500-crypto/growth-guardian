# 只读成长顾问：智能体与 RAG

后端已接入可配置的 LangGraph 智能体、OpenAI Responses / Embeddings 接口和 Qdrant 持久化向量检索。默认关闭，未配置服务时继续返回规则整理结果。前端已提供登录保护的“成长顾问”页面（`/advisor`），接口也可在 `/docs` 调用。鉴权、风险分流、日期与过敏过滤始终由后端执行。

这一版智能体可以在白名单内选择只读工具，并选择本次检索到的知识段落。宝宝事实和食谱候选由原有代码构造，知识以完整审核原文展示；模型不生成自由医学建议或改写知识正文。这是有意保留的安全边界。

```text
已认证用户 → 宝宝归属校验 → 风险/受限问题分流
                           ↓ 普通支持范围内的问题
                  规则工具计算事实/筛选食谱
                           ↓ 显式启用且模型已配置
            LangGraph：检索 → 模型选择 ⇄ 白名单工具
                           ↓
        校验知识ID和原文 → 合并来源/警告 → 结构化回答
                 模型失败则返回原规则结果
```

## 启用与建立索引

在 `backend` 安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

在 `.env` 或部署环境变量中配置：

```dotenv
ADVISOR_AGENT_ENABLED=true
OPENAI_API_KEY=<在本地填写服务密钥，不要提交>
OPENAI_BASE_URL=https://api.openai.com/v1
ADVISOR_MODEL=<所用服务支持的模型ID>
RAG_ENABLED=true
RAG_EMBEDDING_BASE_URL=https://api.openai.com/v1
RAG_EMBEDDING_API_KEY=<Embedding服务自己的密钥>
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_DIMENSIONS=1536
RAG_EMBEDDING_SEND_DIMENSIONS=true
```

模型必须支持 Responses API、函数工具和 JSON Schema Structured Outputs；仅兼容 Chat Completions 的服务不能直接使用此适配器。问答与Embedding使用独立地址和密钥，Embedding不会回退使用问答密钥。已有OpenAI配置要启用RAG，也需单独填写 `RAG_EMBEDDING_API_KEY`。开启模型意味着向该服务发送提问、月龄及本次所需的记录摘要；服务端不发送宝宝姓名、头像、出生日期、记录备注和用户身份字段。提问/食材等用户自行填写内容仍可能含个人信息。调用设置 `store=False`，不等于服务商零保留承诺。

### DeepSeek Flash

DeepSeek官方提供Responses兼容接口，可复用现有适配器。在本地 `.env` 配置（`OPENAI_`前缀是SDK兼容配置名，实际密钥发送到指定的DeepSeek地址）：

```dotenv
ADVISOR_AGENT_ENABLED=true
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=<DeepSeek密钥>
ADVISOR_MODEL=deepseek-flash
RAG_ENABLED=false
```

当前问答模型不能代替Embedding服务；没有独立Embedding配置和审核资料时保持RAG关闭。可先使用模型的工具选择能力。补齐 `RAG_EMBEDDING_BASE_URL`、`RAG_EMBEDDING_API_KEY`、对应模型与维度并导入审核文献后，再设 `RAG_ENABLED=true`。

修改 `.env` 后需重启后端。以下检查不读取宝宝数据库，默认仅查询模型列表；`--tools` 会发送固定测试文本，产生少量模型费用，并验证两轮工具调用和结构化输出。脚本仅输出状态，不输出密钥或原始服务异常：

```powershell
.\.venv\Scripts\python.exe scripts/check_advisor_model.py
.\.venv\Scripts\python.exe scripts/check_advisor_model.py --tools
```

官方依据：[DeepSeek首次调用](https://api-docs.deepseek.com/)、[Responses兼容说明](https://api-docs.deepseek.com/guides/responses_api)。DeepSeek会忽略 `parallel_tool_calls` 等部分参数，后端仍逐个验证并执行白名单工具，用代码限制总调用次数。

### 硅基流动中文Embedding

可在[硅基流动控制台](https://cloud.siliconflow.cn/)创建独立密钥。问答继续使用DeepSeek，向量服务可配置为：

```dotenv
RAG_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
RAG_EMBEDDING_API_KEY=<仅在本地填写硅基流动密钥>
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_EMBEDDING_DIMENSIONS=1024
RAG_EMBEDDING_SEND_DIMENSIONS=false
RAG_ENABLED=false
```

`BAAI/bge-m3`使用固定1024维。官方接口的`dimensions`参数仅支持部分可变维度模型，因此此处不发送该参数；后端仍检查服务实际返回的向量长度、数值有效性和非零向量。模型和维度会写入索引签名，服务或模型变更后需要新集合并重新导入。模型可用性、价格和额度以平台为准。[官方Embedding接口文档](https://docs.siliconflow.cn/docs/api/embeddings-post)。

先检查配置，再单独验证服务；默认检查不发网络请求、不读宝宝库、不打开向量索引。`--probe`只发送一条固定公共测试文本，可能产生少量费用，不代表检索质量或索引内容已验证：

```powershell
.\.venv\Scripts\python.exe scripts/check_knowledge.py
.\.venv\Scripts\python.exe scripts/check_knowledge.py --probe
```

Qdrant 默认存放在 `backend/data/qdrant`，单进程即可运行，无需先启动独立服务。**本地模式运行 API 时，不要同时启动索引脚本；先停止后端，完成导入后重启。** 多 worker / 多实例应通过 `QDRANT_URL` 和可选 `QDRANT_API_KEY` 使用独立 Qdrant 服务。导入凭据应有写权限，API 凭据建议只读。生产服务需限制网络访问。公共集合不保存宝宝记录、提问、模型会话或检索日志。

复制 `docs/knowledge.example.json` 为自己的文献文件，替换正文、真实文献URL、版本、完整适用月龄和主题，由内容审核者确认后填写审核人、日期与有效期并设为 `approved`。示例为 `pending`，不能直接导入。这里的审核字段是管理员离线确认的声明，系统不会自动验证审核人资质；不应自动将抓取内容或旧演示指南标成已审核。只允许公共一般教育资料，不放个人病历、用药剂量或诊疗指令。

首批主题草稿见 `docs/knowledge.candidates.json`，每项均为 `pending`，正式导入器会拒绝。2026-10-23实际读取了WHO中文页面与NHS原始页面后，替换了未能核实的CDC草稿；没有把CDC返回403的请求当作来源核验成功。每条记录保存 `drafted_on`、`source_checked_on`、来源小节 `source_section`、少量原文定位 `source_excerpt` 以及 `content_kind`（中文来源摘要或待审核译文）。正文不是原文全文，短摘录也不能代替完整上下文。来源页面自带的审阅/发布日期不是本应用内容审核日期。

可运行 `scripts/check_candidates.py docs/knowledge.candidates.json` 做离线结构校验；命令不会请求来源、验证作者身份、调用Embedding或建立索引，`source_checked_on`本身仍是维护者记录的核对声明。人工内容审核通过后，应把最终正文和真实审核信息复制到符合 `KnowledgeDocument` 的正式JSON，去除草稿专用字段，填写真实审核人、日期、有效期并设为 `approved`，再运行正式文件的 `--check`。不得伪造专业审核、仅改状态跳过审核，或使用页面审阅人代替本应用审核人。

蜂蜜草稿仅路由到已满月龄0至11，避免把“未满12个月”写成包含12个月。退出某条的路由范围不代表该食物已经安全或获准食用；NHS原文的“超过1岁”及糖限制仍需审核者确认。其他月龄上限是首批资料的保守预览范围，不代表指南在范围外失效。

```powershell
.\.venv\Scripts\python.exe scripts/index_knowledge.py docs/my-reviewed-knowledge.json --check
.\.venv\Scripts\python.exe scripts/index_knowledge.py docs/my-reviewed-knowledge.json
.\.venv\Scripts\python.exe scripts/index_knowledge.py --revoke document-id
```

`--check`整批验证文献契约、重复ID和过期资料，不需要密钥，也不会打开索引或调用Embedding。检查通过仅说明文件符合声明的契约，并不替代内容审核。正式导入同样先校验整批文件，避免后面的格式错误发生时前面的文献已经写入。

文献JSON是1至100项的数组，字段契约见 `KnowledgeDocument`。一个空行分隔一个完整知识段落，每段最多1200字，不进行机械截断。嵌入输入为标题和原段落，检索显示原段落。同一 `document_id` 重复导入幂等，修改版本/内容时先写新段落，再删除旧段落；写入不是跨文献事务，导入中断后可重试。撤销后不再检索；不要试图靠导入 `pending` 文献来撤销旧版。

模型/维度/服务地址被写入索引向量名称；任何一项变更需用新的 `QDRANT_COLLECTION` 重新导入，不能混用向量空间。默认 TopK=3、最低余弦相似度0.55，可通过环境变量调整；阈值需按审核语料离线评估，分数不是可信度。

资料必须审核通过、主题匹配、月龄匹配、在查询日已经审核且当前仍有效，才会返回。检索后还会读取当前过敏清单，保守排除正文提及已知过敏源或常见同类名的整段资料；这会同时排除一些避敏说明，并不能识别所有别名、未知过敏或交叉污染。清单无效时暂停知识摘录；问题报告具体食材过敏时，知识问答先要求核实档案。检索不到时明确缺资料。过期资料即使对历史日期查询也不再使用；当前集合只保留当前版本，不提供完整历史文献重放。没有审核资料时不自动使用站内演示FAQ/指南。

### 检索效果评估

复制`docs/knowledge-evaluation.example.json`，用公共测试问题和人工确认的相关`document_id`替换占位内容。覆盖能回答、没有资料、错误月龄/主题、审核前日期、过期资料和不应命中的文献。一个用例要么给出非空`expected_document_ids`，要么设`expect_empty=true`；可用`forbidden_document_ids`标记禁止命中的文献。不要放真实宝宝记录、身份或原始个人提问。脚本会将测试问题发送给配置的Embedding服务，但不调用问答模型。

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_knowledge.py docs/my-public-evaluation.json --check
.\.venv\Scripts\python.exe scripts/evaluate_knowledge.py docs/my-public-evaluation.json
```

使用当前`RAG_TOP_K`和`RAG_MIN_SCORE`，输出文献级命中率、平均召回/精确率、MRR、预期无结果准确率与逐例文献ID，不输出问题原文、知识正文、凭据或原始服务异常。一个文献有多个段落时先按返回顺序去重；正例全部相关文献命中且没有禁止文献才算通过。检索异常判为失败，不能算成正确的无结果。`--check`只验证文件，不访问服务或索引。空集合无法通过正例。

该评估只覆盖向量候选和元数据过滤；不覆盖问答模型的最终知识选择、宝宝过敏排除、完整医学分流和真实应用效果。过敏与模型选择仍由独立回归测试覆盖。占位示例及假Embedding单元测试不能证明真实检索质量。标注集和索引内容准备完成、评估结果人工核对后再设`RAG_ENABLED=true`并重启后端；脚本不会自行开启RAG。

### 待审核资料的隔离预览

`scripts/preview_candidates.py`专用于开发阶段验证Embedding和检索，不调用正式 `KnowledgeStore` 或宝宝数据库，也不调用问答模型。只接受有来源核对记录的公共草稿；标签必须引用包内文献，正例必须与月龄、主题和日期声明一致。校验无法判定问题/资料是否包含隐私，操作者仍须确认文件完全公开。当前17条问题是为这5条资料编写的草稿标签，并非独立专家标注或保留测试集。

```powershell
# 不联网、不创建索引
.\.venv\Scripts\python.exe scripts/preview_candidates.py docs/knowledge.candidates.json docs/knowledge-evaluation.draft.json --check

# 发送公开正文和合成问题，可能产生少量Embedding费用
.\.venv\Scripts\python.exe scripts/preview_candidates.py docs/knowledge.candidates.json docs/knowledge-evaluation.draft.json --compare-thresholds .6 .65 .7 --output docs/knowledge-preview.report.json
```

预览固定创建内存Qdrant，payload保留 `pending`，不读取配置中的索引路径或远程Qdrant地址，不转成 `approved`，结束关闭且不持久化向量。比较阈值时同次运行缓存查询向量、最后释放，不重复发同一个问题的Embedding请求。当前5个段落、17条问题共18次请求、22段文本。来源短摘录和审核备注不发送给Embedding；仅发送标题、正文和公开测试问题。脚本不会修改 `.env` 或 `RAG_ENABLED`。

报告只包含文献ID、分数、聚合指标、来源文件哈希和隔离标记，不写问题、正文、密钥或原始异常。写入失败或服务异常不能算评估通过。预览日期过滤采用草稿生成/来源核对日期，而非审核日期；不评估正式资料的审核、有效期或过敏过滤。`--output`仅允许另存JSON，不能覆盖两个输入文件。报告中的 `passed`仅表示本次草稿标签的检索条件通过，不表示每个候选都相关、内容已通过审核或服务可以上线。

2026-10-23真实 `BAAI/bge-m3`（1024维）预览：最新默认0.55阈值运行17/17通过、平均召回1.0、平均精确率0.7361，无检索错误；此前同文件第一次运行16/17通过，“牙刷护理”问题误返回蜂蜜资料。差异原因尚未确定，首次和第二次摘要保存在 `docs/knowledge-preview.observations.json`，最新含逐例分数的完整报告在 `docs/knowledge-preview.report.json`。不能只挑一次全通过作为稳定性结论。

同次阈值比较中，0.60为17/17、平均精确率0.8194，0.65降为14/17、平均召回0.75，0.70降为9/17、平均召回0.375。这只是小型草稿集上的观测，不据此修改生产阈值；还需要更大的独立正负例、重复稳定性检查，以及内容和最终回答审核。应用RAG仍关闭。

### 重复检索与挑战集

新增30条合成挑战问题在 `docs/knowledge-evaluation.challenge.json`，与原17条回归问题分开存放。`scripts/check_retrieval_stability.py`检查两集的用例ID及规范化文本不重合；这只防止直接重复，不代表专家独立标注或语义独立。单次合计最多100例、200段去重嵌入文本，重复2至5轮。`--check`离线校验并显示预计请求数；不访问服务或打开任何索引。

```powershell
.\.venv\Scripts\python.exe scripts/check_retrieval_stability.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --single-probe-case-id unsupported-topic-content --repeats 3 --check
.\.venv\Scripts\python.exe scripts/check_retrieval_stability.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --single-probe-case-id unsupported-topic-content --repeats 3 --output docs/knowledge-stability.report.json
```

每轮重新请求向量，再固定本轮向量分别进行同索引重放和重建内存索引重放，区分向量变化与索引复现问题。可用`--single-probe-case-id`额外对照最多5例的单条Embedding请求，不能用批量请求的一致性推断所有线上调用都一致。服务失败即停止后续付费重复，不回显原始异常。报告保留向量指纹、归一化差异、阈值前候选及失败用例，不保存原始向量、问题或正文。指纹变动不一定导致候选变化；`retrieval_stable=true`也不代表标签验收通过。

2026-10-23本轮三次均42/47通过，而非之前17题单次运行的全通过：两处漏检、三处误召回；同向量检索和重建索引一致，6/52段输入出现小幅向量变化，但本轮候选未改变。牙刷问题再次以0.55059分误召回蜂蜜条目，接近0.55阈值。详见最新 `docs/knowledge-stability.report.json` 及诊断结论 `docs/knowledge-stability.findings.md`。该结果尚不能确认历史波动的确定根因，也没有验证智能体的最终知识选择；正式RAG仍关闭。

## 接口

`GET /api/v1/babies/{baby_id}/advisor/status` 同样需要登录并校验宝宝归属，仅返回 `agent` / `knowledge` 配置标记（`disabled` / `unconfigured` / `configured`）以及上海时区 `today`。配置完成不保证服务在线或知识集合已有审核内容；该接口不调用模型、不打开向量库，不暴露凭据和服务地址。

`POST /api/v1/babies/{baby_id}/advisor/ask`，需要现有 Bearer 登录令牌，成功响应继续使用项目的 `{code, message, data}` 包装。

```json
{
  "question": "总结最近一周吃了什么",
  "intent": "diet_review",
  "as_of": "2026-10-23",
  "days": 7
}
```

- `question`：2-500字，去除首尾空白。
- `intent`：可选，`growth_review` / `diet_review` / `recipe_recommendation` / `feeding_knowledge`。未传时按有限关键词识别；知识问答建议显式传 `feeding_knowledge`。不支持的提问返回 `clarification_needed`。显式意图不能跳过风险分流。
- `as_of`：可选，默认上海时区今天，范围为宝宝出生日至今天。
- `days`：饮食回顾天数，1-31，默认7，包含 `as_of` 当天。日期范围由字段确定，不解析自然语言中的任意日期表达。
- `nutrition`：可选目录营养标签筛选，最多20字；目录标签不代表实际营养测算。
- 拒绝未声明字段，包括 `user_id`、请求体中的 `baby_id`、`exclude_allergens` 和写入指令。

## 前端使用

从主导航或宝宝概览的顾问入口进入，选择示例问题或自行输入，再点击“开始整理”。示例按钮只填写表单，不触发模型调用。可以指定回顾内容、截至日期和饮食天数；自然语言中的日期不会覆盖表单设置。

页面分别展示记录事实、辅食候选、审核知识原文、需要留意的事项和信息缺口。点击编号可以展开并定位依据；知识来源可查看原文链接、版本和审核日期。模型失败时明确提示回退到记录整理；紧急分流显示求助提示。

问题与结果仅保存在当前页面内存中，刷新或切换宝宝会清空；不写入浏览器持久存储。切换宝宝、离开页面或点击“停止等待”会取消浏览器等待并忽略迟到响应，但后端或模型请求可能继续处理。前端为顾问提问单独设置390秒超时，部署代理也需允许相应请求时长。页面在提交前说明启用模型时会发送问题、月龄和所需记录摘要；前端不接收或保存服务密钥。

## 输出

### 完整RAG隔离自检

`scripts/check_rag_pipeline.py`将真实HTTP路由、JWT认证与归属、风险分流、Embedding/Qdrant、LangGraph工具循环、云端模型、引用校验和最终结构化响应串起来。该脚本固定使用SQLite内存业务库及内存向量集合，不启动正式应用生命周期，不连接真实宝宝数据库。`--check`只验证输入；真实运行会发送公开问题、公开草稿和合成软件测试资料给已配置的模型/Embedding服务，须确认数据公开并接受相应API用量。

```powershell
.\.venv\Scripts\python.exe scripts/check_rag_pipeline.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --check
.\.venv\Scripts\python.exe scripts/check_rag_pipeline.py docs/knowledge.candidates.json docs/knowledge-evaluation.challenge.json --regression-cases docs/knowledge-evaluation.draft.json --output docs/rag-pipeline.report.json
```

公共草稿以显式的 `candidate_preview` 运行范围进入相同图和引用校验流程：来源仍为pending、不填审核日期，模型指令和摘要均注明隔离测试。该模式不是用户API参数，正式请求不接受它；默认正式图拒绝预览来源。另用一条非医学合成approved夹具测试原正式知识工具，绝不把WHO/NHS草稿改成approved。

2026-10-23真实结果：47题结构47/47通过、最终文献选择45/47通过、安全及故障降级9/9通过。3个高分但无关的召回被模型排除；2个变体问法仍因召回不足返回无资料。机器报告保留 `status=failed`，未修改阈值/标签、`.env`或正式索引。详见 [完整链路检查结论](rag-pipeline.findings.md)。这不替代内容批准、独立质量验证或生产前端/代理测试。

### 候选召回优化实验

新增可选配置 `RAG_RETRIEVAL_STRATEGY=baseline|expanded|hybrid`，默认仍为baseline。`RAG_CANDIDATE_TOP_K=5`与`RAG_CANDIDATE_MIN_SCORE=0.45`仅在非baseline策略中扩展候选，不代表可直接引用；模型仍最多选择3个本次返回ID，服务端继续原文校验。hybrid在相同元数据过滤后执行有界字面排序并与向量排名融合，`RAG_LEXICAL_SCAN_LIMIT=200`超限会失败关闭。纯字面候选的`score`为null，不伪造余弦分数，融合值单列`fusion_score`。

本地 `.env`没有采用这些新策略。`scripts/compare_retrieval.py`先用已观察的47题开发集比较三种候选策略，再固定选择并只对新增24条合成题运行baseline/选中策略。新题不能反过来选择策略；每次运行内复用文本向量，以隔离向量波动。详见 [固定协议](retrieval-optimization.protocol.md)。

2026-10-26代码及离线校验已实施，隔离云端比较实际完成：开发集baseline为45/47，expanded与hybrid均为47/47，按精确选择选择hybrid；新增24题中baseline为23/24（葡萄问题漏召回），hybrid为23/24（婴儿粥比例无资料题误引用）。安全检查和结构检查均通过，正式RAG继续关闭，公共草稿仍为pending。完整数字、请求量和隔离校验见 [召回优化实施状态](retrieval-optimization.findings.md) 与 `retrieval-comparison.report.json`。

针对上述误引用，混合召回已增加通用的精确事实证据门控：比例、数量、温度、时长、次数等问题若没有去除泛化上下文词后的实质字面重合，则返回空候选，不把低证据密集相似度交给模型选择。该修复已由离线检索测试覆盖，但不能重写旧云端报告或替代新独立验证集；当前环境未重新调用云端服务，正式RAG仍关闭。

### 回答字段

`data` 使用 `AdvisorAnswer`，包含 `schema_version`、服务端生成的 `request_id`、`generation_mode`、`agent_status`、`as_of`、`intent`、`safety_level`、`summary`、`observations`、`recommendations`、`risks`、`missing_information`、`sources`、`recipe_candidates`、`knowledge`、`tool_statuses`、`actions`、`disclaimer`。OpenAPI 提供完整 JSON Schema。

`generation_mode` 为 `rules`（规则）、`agent`（智能体运行成功但没有知识引用）、`agent_rag`（智能体运行成功且引用知识）。`agent_status` 为 `disabled`、`completed`、`unavailable`（模型配置不足）、`failed`（异常/超限/非法输出后降级）或 `skipped_safety`（安全或范围分流未调用模型）。知识摘录放在 `knowledge` 的 `text` / `evidence_id`，关联 `sources` 的文献URL、版本和审核日期。来源编号包含 `knowledge:` 前缀及稳定段落ID，只接受本次检索实际返回的ID和对应原文。

事实观察必须包含有效的 `evidence_ids`；来源编号不能重复。来源必须与本次工具返回内容一致；候选食谱的标题、食材和目录标签必须与工具结果一致。v1 的 `actions` 强制为空，不能生成或执行写操作。校验失败时返回固定提示，不回显未通过校验的结果。

`safety_level` 仅表示本次回答的处理方式，不是宝宝的健康等级：

| 值 | 含义 |
| --- | --- |
| normal | 普通记录整理，未触发额外提示 |
| caution | 信息缺失、数据过期、有限筛选、需要澄清或核实 |
| urgent | 文字匹配到需及时联系儿科/急诊的表述 |
| emergency | 文字匹配到可能需要立即急救的表述，优先提示求助 |

## 工具边界

`AdvisorTools` 在构造时接收后端已认证用户ID，并校验宝宝归属。每个实例只服务本次请求，方法不能改传用户或宝宝身份；不暴露通用 SQL、任意函数调用或 HTTP 工具端点。

| 工具 | 返回范围 |
| --- | --- |
| get_baby_profile | 档案性别、按指定日计算的月龄；不输出姓名、照片或出生日期 |
| get_growth_summary | 近90天最多180条测量；每项指标独立取最新值，比较两个不同日期的记录 |
| get_growth_curve | 同一有界窗口的原始有效测量点；不使用近似WHO表计算临床分位 |
| get_milestones | 截至查询日最多50条已记录里程碑；未记录不代表未达成 |
| get_diet_summary | 1-31天最多500条；累计有效的已录入奶量、时长、辅食次数和食材 |
| get_allergies | 当前过敏清单；无记录明确返回 no_data，不代表没有过敏 |
| recommend_safe_recipes | 最多筛选200条适龄目录记录，返回最多5个候选；强制排除已知过敏源及常见同类，配料不明的复合食材不推荐 |
| search_reviewed_knowledge | Qdrant语义检索；后端固定主题/月龄/日期，返回最多5个审核原文段落及可追溯来源 |
| search_feeding_guides | 当前站内演示指南，明确标记 unverified |
| search_feeding_faqs | 字面关键词检索，最多5条，明确标记 unverified |

工具统一返回 `tool`、`schema_version`、`status`、`baby_id`、`data`、`evidence`、`warnings`、`missing`。`status` 为 `ok` / `partial` / `no_data` / `invalid`，截断或信息不全必须明示。

成长比较只是数值差，不推断疾病或发育是否正常；同一天多条记录取最新ID，不构造日内生长速度。缺少有效奶量不能计成0摄入；母乳时长不换算奶量，现有记录也不能用于计算热量和营养达标情况。

历史查询只对测量和饮食等有日期的记录提供范围过滤。过敏清单、档案和食谱目录没有历史版本，使用当前状态并在相关结果中明示，不能视为历史状态重放。

## 安全边界

先验证归属，再做文字风险分流；高风险分支不继续读取成长、饮食和食谱。诊断、用药及写入请求返回支持范围。提问中出现具体食材过敏时，先要求核实档案，避免仅按旧清单推荐。

风险初筛只有有限中英文表述及简单否定/假设句处理，无法替代完整医学分诊，未命中不能解释为安全。食材同类映射同样是有限的保守排除规则，不保证识别全部别名、未知过敏或交叉污染。上线健康建议前仍需专业内容审核与独立场景评估。

现有指南和FAQ缺少可追溯文献、版本和审核信息，不进入向量集合，不作为模型工具暴露。当前WHO参考数据是近似绘图值，不参与健康判断。审核知识与宝宝事实分开展示，公共资料不能证明某个宝宝的诊断或食材耐受。

模型最多3轮、6次工具调用，均可配置上限，每个工具最多请求一次，重复工具结果在本次请求内复用。参数固定为空对象，模型不能更改用户、宝宝、日期、饮食天数、目录标签和过敏过滤；不提供任意SQL、网络工具和写操作。每次请求独立图状态，无持久化会话，不开启LangSmith追踪。模型输出只有知识ID列表，任何未知ID、未授权工具、额外参数、超限、拒答或服务异常都安全降级。

应用日志只记录请求编号、意图、分流等级、智能体状态和工具状态，不记录问题原文、姓名、原始记录或令牌。业务记录不写入。模型/向量SDK异常不会原样输出。结构和来源校验不能替代医学内容审核、检索相关性评估或完整医学分诊。

验证：在 `backend` 下运行 `.\.venv\Scripts\python.exe -m pytest tests/test_advisor.py tests/test_advisor_agent.py tests/test_knowledge.py -q -p no:cacheprovider`。测试使用SQLite内存业务库、临时本地Qdrant和假模型/Embedding，验证工具循环、权限与安全、原文引用、失败降级、索引持久化、更新撤销及元数据过滤；不调用付费服务，不构成真实模型质量或医学效果评估。

接口依据：[官方函数调用文档](https://developers.openai.com/api/docs/guides/function-calling)、[结构化输出文档](https://developers.openai.com/api/docs/guides/structured-outputs)、[Embeddings文档](https://developers.openai.com/api/docs/guides/embeddings)。
