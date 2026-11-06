# 宝宝辅食与成长记录软件 - 后端服务

基于 FastAPI + SQLAlchemy 2.x + MySQL 的响应式 Web 应用后端，覆盖用户、宝宝档案、成长记录、饮食记录、辅食食谱、智能推荐、喂养指南、通知等完整业务链路。

- 在线交互式 API 文档（启动服务后访问）：`http://127.0.0.1:8000/docs`（Swagger UI）或 `/redoc`
- 一键测试控制台（启动服务后访问，仅 `DEBUG=true` 环境可用）：`http://127.0.0.1:8000/static/test-runner.html`
- 健康检查：`GET /health`

---

## 技术栈

| 类别 | 选型 |
| --- | --- |
| Web 框架 | FastAPI |
| ORM | SQLAlchemy 2.x |
| 数据库 | MySQL 8.0（开发/生产）、SQLite（测试） |
| 数据库驱动 | PyMySQL |
| 认证授权 | JWT（HS256，有效期由 `ACCESS_TOKEN_EXPIRE_MINUTES` 配置）+ bcrypt 密码哈希 |
| 数据校验 | Pydantic v2 |
| 日志 | logging + TimedRotatingFileHandler（按天滚动，保留 30 天） |
| 测试 | pytest + httpx TestClient（内存 SQLite） |

## 目录结构

```
backend/
├── app/
│   ├── main.py            # 应用入口：中间件、异常处理器、生命周期建表与种子
│   ├── api/v1/            # 路由层：auth/users/babies/growth/diet/recipes/advice/notifications
│   ├── core/              # 配置、数据库、安全、异常、日志、依赖注入
│   ├── models/            # ORM 模型（12 张表）
│   ├── schemas/           # Pydantic 请求/响应模型
│   ├── services/          # 业务逻辑（成长印记、营养聚合、智能推荐等）
│   └── seed/              # 种子数据（食谱/指南/FAQ/演示账号）
├── tests/                 # pytest 测试（14 个测试文件，117 个用例，分层覆盖单元/集成/数据库/迁移/契约/限流/WHO）
├── scripts/               # 临时诊断脚本
├── .env / .env.example    # 环境配置
├── requirements.txt
└── pytest.ini
```

## 快速启动

### 1. 环境要求

- Python 3.10+（**版本偏差说明**：立项书要求 Python 3.11+，当前实际 venv 为 **3.10.11**；代码使用 `X | None` 类型语法与 SQLAlchemy 2.x，均兼容 3.10，功能不受影响。后续如需 3.11 专属特性（如 `except*`、`tomllib`），需先升级 venv 并回归全部测试）
- MySQL 8.0（本地已建库 `baby_growth`，字符集 `utf8mb4`）

### 2. 创建虚拟环境并安装依赖

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并按需修改：

```ini
DATABASE_URL=mysql+pymysql://baby_user:<your-db-password>@127.0.0.1:3306/baby_growth?charset=utf8mb4
SECRET_KEY=please-generate-a-random-64-char-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
LOG_LEVEL=INFO
```

> 生产环境必须通过环境变量注入强随机 `SECRET_KEY` 与数据库凭据，禁止使用默认值。生产环境凭据必须通过环境变量注入，禁止写入仓库。

### 4. 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动时自动完成：

- 数据库结构初始化按模式分流（详见「数据库迁移（Alembic）」章节）：开发/测试模式（`DEBUG=True`）使用 `Base.metadata.create_all` 直接建表；生产模式（`DEBUG=False`）自动执行 Alembic `upgrade head`，`create_all` 已在生产停用；
- 写入种子数据（幂等）：25 条食谱、7 条分月龄喂养指南、12 条常见问题、演示账号与演示宝宝。

### 5. 启动前端

前端工程位于仓库根目录 `frontend/`，技术栈 Vue 3 + Vite + TypeScript + Pinia + Vue Router + Axios：

```powershell
cd frontend
npm install
npm run dev        # 开发服务器 http://localhost:5173，代理 /api → http://127.0.0.1:8000
```

其他常用命令：`npm run test`（单元测试）、`npm run build`（生产构建）。

### 6. 运行测试

```powershell
$env:PYTHONDONTWRITEBYTECODE=1
.\.venv\Scripts\python.exe -m pytest -c pytest.ini -q
```

测试使用内存 SQLite（`sqlite://` + StaticPool），会话级建表与种子，不依赖 MySQL，可直接运行。当前共 **117 个用例，全部通过**，分层覆盖：单元（`test_unit_growth`）、集成（`test_auth`/`test_babies`/`test_growth`/`test_diet`/`test_recipes`/`test_advice`/`test_notifications`）、数据库约束（`test_database`）、迁移链（`test_migrations`）、安全契约（`test_contract`）、登录限流（`test_login_rate_limit`）、WHO 参考线（`test_who_reference`）、系统工具（`test_system`）。

### 7. 一键启动测试（测试控制台）

启动服务后访问 `http://127.0.0.1:8000/static/test-runner.html`：

- 点击「一键启动测试」按钮，后端创建测试任务并后台执行 pytest；
- 页面通过轮询实时反馈三种状态：**运行中**（旋转加载 + 圆环进度）、**成功**（绿色 + 100% 圆环）、**失败**（红色 + 失败用例明细）；
- 展示用例总数 / 通过 / 失败 / 跳过统计与耗时；
- 按 "Warm Growth Space" 设计系统实现，适配移动端与桌面端。

相关接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/system/run-tests` | 创建测试任务（后台执行 pytest） |
| GET | `/api/v1/system/test-tasks/{task_id}` | 轮询任务状态与结果 |

> **安全限制**：system 路由由 `app/main.py` 按 `settings.DEBUG` 条件注册，**仅 `DEBUG=true`（开发/测试环境）可用**；生产环境（`DEBUG=False`）不注册该路由，访问返回 **404**，避免暴露服务端执行 pytest 的调试能力。

## 演示账号

| 手机号 | 密码 | 说明 |
| --- | --- | --- |
| `13800000000` | `123456` | 演示账号，已绑定 8 个月宝宝「豆豆」，含生长/饮食/里程碑种子数据 |

## 统一响应格式

所有 `/api/v1` 下的 JSON 响应（成功与业务失败）统一为：

```json
{
  "code": 0,
  "message": "ok",
  "data": { }
}
```

- `code = 0` 表示成功；非 0 为业务错误码（见下表）；
- 业务错误统一返回 **HTTP 200 + 业务码**（40100 未认证 / 40300 无权限 / 40400 不存在 / 40900 冲突 / 42200 参数校验失败 / 42900 请求过于频繁）；服务器未捕获异常返回 **HTTP 500 + 50000**。

业务错误响应示例（HTTP 200）：

```json
{
  "code": 40100,
  "message": "请先登录",
  "data": null
}
```

### 业务错误码

| code | 含义 | HTTP 状态 |
| --- | --- | --- |
| 40100 | 未认证 / 令牌无效或过期 | 200 |
| 40300 | 无权限访问该资源 | 200 |
| 40400 | 资源不存在 | 200 |
| 40900 | 数据冲突（如重复注册、过敏食材重复记录） | 200 |
| 42200 | 请求参数校验失败（含分页 page/page_size 非法） | 200 |
| 42900 | 请求过于频繁（登录连续失败触发限流锁定） | 200 |
| 50000 | 服务器内部错误（未捕获异常兜底） | 500 |

## 认证方式

- 注册/登录后获得 `access_token`（HS256 JWT，有效期由配置项 `ACCESS_TOKEN_EXPIRE_MINUTES` 读取，默认 120 分钟）；
- 业务接口需在请求头携带：`Authorization: Bearer <access_token>`；
- 未携带或令牌失效返回业务码 `40100`（HTTP 200）。

**登录限流**：同一手机号连续 5 次密码错误后锁定 15 分钟，锁定期内登录请求直接返回业务码 `42900`（提示"登录失败次数过多，请15分钟后重试"）；登录成功或锁定到期后计数清零。限流器为内存实现（`app/core/rate_limit.py`），适用于单进程部署，多副本部署需替换为 Redis 等共享存储。

## API 接口清单

> 所有路径均以 `/api/v1` 为前缀；除标注「公开」外，均需 Bearer Token。

### 1. 认证与用户（auth / users）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register` | 用户注册（公开） |
| POST | `/auth/login` | 用户登录，返回 JWT（公开）。同一手机号连续 5 次失败锁定 15 分钟，返回 `42900` |
| GET | `/users/me` | 获取当前用户信息 |
| PUT | `/users/me` | 更新当前用户信息 |

### 2. 宝宝档案（babies）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/babies` | 创建宝宝档案 |
| GET | `/babies` | 宝宝档案列表 |
| GET | `/babies/{baby_id}` | 档案详情 |
| GET | `/babies/{baby_id}/summary` | 成长印记聚合数据（月龄/阶段/最新身高体重） |
| PUT | `/babies/{baby_id}` | 更新档案 |
| DELETE | `/babies/{baby_id}` | 删除档案 |

### 3. 成长记录（growth）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/babies/{baby_id}/growth-records` | 新增生长记录 |
| GET | `/babies/{baby_id}/growth-records` | 生长记录列表 |
| GET | `/babies/{baby_id}/growth-curve` | 生长曲线数据（按体重/身高/头围分组的曲线点；0-24 月龄宝宝附 `who_reference` 可选字段，即 WHO 2006 精简参考线 P3/P15/P50/P85/P97 分位点，超过 24 月龄该字段为 `null`） |
| DELETE | `/growth-records/{record_id}` | 删除生长记录 |
| GET | `/babies/{baby_id}/milestones` | 里程碑列表 |
| POST | `/babies/{baby_id}/milestones` | 新增里程碑 |
| DELETE | `/milestones/{milestone_id}` | 删除里程碑 |

### 4. 饮食记录（diet）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/babies/{baby_id}/diet-records` | 新增饮食记录（母乳 breast_milk / 配方奶 formula / 辅食 solid_food） |
| GET | `/babies/{baby_id}/diet-records` | 饮食记录列表（按日期筛选，标准分页 `page`/`page_size`，非法值返回 `42200`） |
| PUT | `/diet-records/{record_id}` | 更新饮食记录 |
| DELETE | `/diet-records/{record_id}` | 删除饮食记录 |
| GET | `/babies/{baby_id}/diet-analysis` | 营养摄入聚合分析 |
| GET | `/babies/{baby_id}/allergies` | 过敏食材列表 |
| POST | `/babies/{baby_id}/allergies` | 新增过敏食材 |
| DELETE | `/allergies/{allergy_id}` | 删除过敏食材 |

### 5. 辅食推荐（recipes）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/recipes` | 食谱列表与多维筛选（月龄/食材/营养/关键词，分页） |
| GET | `/recipes/favorites` | 我的收藏 |
| GET | `/recipes/{recipe_id}` | 食谱详情 |
| POST | `/recipes/{recipe_id}/favorite` | 收藏食谱（幂等） |
| DELETE | `/recipes/{recipe_id}/favorite` | 取消收藏（幂等） |
| GET | `/babies/{baby_id}/recipes/recommendations` | 智能推荐（月龄适配 + 过敏规避，标准分页 `page`/`page_size`，可选 `nutrition` 筛选） |
| GET | `/babies/{baby_id}/meal-plans?week_start=YYYY-MM-DD` | 获取一周辅食计划 |
| PUT | `/babies/{baby_id}/meal-plans` | 整体保存一周辅食计划 |

### 6. 喂养指导（advice）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/guides?month=8` | 分月龄喂养指南 |
| GET | `/faqs?keyword=辅食` | 常见问题检索 |

### 7. 通知（notifications）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/notifications` | 通知列表（支持 `unread_only` 过滤，标准分页 `page`/`page_size`） |
| GET | `/notifications/unread-count` | 未读数量 |
| PATCH | `/notifications/{notification_id}/read` | 标记单条已读 |
| PATCH | `/notifications/read-all` | 全部标记已读 |

### 8. 分页响应结构

`diet-records`、`recipes/recommendations`、`notifications` 三个列表接口已统一为标准分页：请求携带 `page`（从 1 起，ge=1）与 `page_size`（1-100，默认 20），非法值由全局校验处理器返回 `42200`。响应 `data` 为统一分页结构：

```json
{
  "items": [ ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

## 数据库设计（12 张表）

> 以下字段与 `backend/app/models/*.py` 实际 ORM 定义逐一核对。

| 表 | 说明 | 关键字段 |
| --- | --- | --- |
| `users` | 用户 | id、phone（String(20)，唯一+索引）、password_hash（bcrypt）、nickname、avatar_url（可空）、is_active（默认 True）、created_at / updated_at |
| `babies` | 宝宝档案 | id、user_id（FK users.id，CASCADE，索引）、name、gender（可空，male/female）、birth_date、avatar_url（可空）、is_default（默认 False）、created_at / updated_at |
| `growth_records` | 生长记录 | id、baby_id（FK，CASCADE，索引）、record_date（索引）、weight_kg / height_cm / head_circumference_cm（Float，均可空）、note（可空）、created_at |
| `milestones` | 成长里程碑 | id、baby_id（FK，CASCADE，索引）、milestone_type（如 roll_over/sit/crawl/walk）、name、achieved_at、note（可空）、created_at |
| `diet_records` | 饮食记录 | id、baby_id（FK，CASCADE，索引）、record_date（索引）、record_type（breast_milk/formula/solid_food）、details（JSON，类型化明细，可空）、note（可空）、created_at |
| `allergies` | 过敏食材 | id、baby_id（FK，CASCADE，索引）、ingredient（String(50)，索引）、severity（mild/moderate/severe，可空）、note（可空）、created_at |
| `recipes` | 辅食食谱 | id、title、cover_url（可空）、suitable_age_min / suitable_age_max、ingredients（JSON）、steps（JSON）、nutrition_tags（JSON）、tips（可空）、is_active（默认 True）、created_at |
| `recipe_favorites` | 食谱收藏 | id、user_id（FK，CASCADE，索引）、recipe_id（FK，CASCADE，索引）、created_at；**唯一约束** `uq_recipe_favorites_user_recipe(user_id, recipe_id)` 数据库层兜底收藏幂等（D07） |
| `meal_plans` | 一周辅食计划 | id、baby_id（FK，CASCADE，索引）、week_start（索引）、day_of_week（0-6）、meal_type（breakfast/lunch/dinner/snack）、recipe_id（可空，FK recipes.id，SET NULL）、note（可空）、created_at；**唯一约束** `uq_meal_plans_slot(baby_id, week_start, day_of_week, meal_type)` 兜底计划槽位唯一（D07） |
| `guides` | 分月龄喂养指南 | id、month_start、month_end、title、content（Text）、food_suggestions（JSON）、created_at |
| `faqs` | 常见问题 | id、category（索引）、question、answer（Text）、keywords（**String(200)，空格分隔的检索关键词**，可空——非 JSON）、created_at |
| `notifications` | 站内通知 | id、user_id（FK，CASCADE，索引）、**notify_type**（milestone/reminder/recommendation/system，默认 system）、title、content（Text）、is_read（默认 False）、created_at |

**索引与约束说明**：

- 所有外键（`user_id`、`baby_id`、`recipe_id`）均带单列索引；用户/宝宝侧删除为 CASCADE 级联清理，`meal_plans.recipe_id` 删除食谱时置 NULL（SET NULL）不级联删计划；
- 高频查询列建索引：`babies` 按 `user_id`、`growth_records`/`diet_records` 按 `baby_id` + `record_date`、`allergies` 按 `ingredient`、`faqs` 按 `category`、`meal_plans` 按 `week_start`；
- 两个复合唯一约束（`uq_recipe_favorites_user_recipe`、`uq_meal_plans_slot`）在数据库层保证幂等与槽位唯一，应用层仅作前置查重，并发场景由约束兜底（IntegrityError 回滚后按幂等语义处理）。

## 只读成长顾问

新增 `POST /api/v1/babies/{baby_id}/advisor/ask`，支持成长测量回顾、饮食记录汇总和按月龄/已知过敏史筛选食谱候选。接口使用现有登录认证和宝宝归属校验，返回带来源、信息缺口、工具状态及风险提示的结构化结果。

已接入可配置的 LangGraph 只读智能体与 Qdrant 向量检索，支持 `feeding_knowledge` 知识摘录。默认仍可无密钥使用规则回答；启用智能体需要配置模型服务，RAG需要先导入带来源/版本/月龄/有效期的已审核公共资料。模型只能选择许可工具及检索原文，不能写记录或生成任意医疗建议。登录前端后可从“成长顾问”（`/advisor`）提问、查看记录依据和知识摘录。`GET /api/v1/babies/{baby_id}/advisor/status` 返回当前功能配置标记，不检查模型连通性或索引内容。启用步骤、索引命令和安全边界见 [docs/advisor.md](docs/advisor.md)。

支持硅基流动`BAAI/bge-m3`固定1024维Embedding；通过`RAG_EMBEDDING_SEND_DIMENSIONS=false`省略该模型不支持的维度参数。`scripts/check_knowledge.py --probe`可用固定公共文本检查服务；`scripts/index_knowledge.py <文献文件> --check`可在导入前整批预校验；`scripts/evaluate_knowledge.py <公开评估文件>`可评估检索候选与元数据过滤。检查和评估均不会读取宝宝数据库或自行启用RAG。

首批5条公共资料草稿位于 `docs/knowledge.candidates.json`，已记录实际读取的WHO/NHS来源、小节、核对日期及简短原文定位，但中文摘要/译文和月龄路由仍是 `pending`。`scripts/check_candidates.py`只做结构检查。正式索引命令会拒绝草稿；须由内容审核者确认完整上下文、正文、月龄、地区适用性和有效期，再生成有真实审核记录的正式文件。

`scripts/preview_candidates.py docs/knowledge.candidates.json docs/knowledge-evaluation.draft.json --check`可离线校验资料与17条草稿标签；去掉`--check`可用真实Embedding在内存Qdrant评估，不触碰正式集合、不读宝宝数据库、不自动启用RAG。支持`--compare-thresholds .6 .65 .7 --output docs/knowledge-preview.report.json`复用向量对比阈值。最新真实报告和前两次结果差异记录分别见 `docs/knowledge-preview.report.json`、`docs/knowledge-preview.observations.json`；单次全通过不等于独立验证或医学内容审核完成。详见 [隔离预览说明](docs/advisor.md#待审核资料的隔离预览)。

后续增加30条单独的合成挑战问题和 `scripts/check_retrieval_stability.py`，支持多轮新向量采样、固定向量重放、重建内存索引及单条/批量请求对照。最新47题三轮均42/47通过，检索质量未验收；6段输入有微小向量变化，本轮候选保持一致。最新诊断以 `docs/knowledge-stability.report.json` 和 [检查结论](docs/knowledge-stability.findings.md) 为准，不能用旧17题全通过报告代替。脚本不改变正式阈值或开启RAG。

完整链路已增加 `scripts/check_rag_pipeline.py`：真实API认证/归属、云端Embedding、内存Qdrant、LangGraph、DeepSeek选择、原文引用与结构化输出。2026-10-23实测47题结构47/47通过、最终文献选择45/47通过、安全/降级9/9通过；真实模型过滤了3个误召回，但仍有2个漏召回，整体质量状态为未通过。详情见 [完整自检结论](docs/rag-pipeline.findings.md) 和 `docs/rag-pipeline.report.json`。公共草稿保持pending；只使用公开/合成测试数据，未触碰正式索引或开启正式RAG。

后续已实施可选expanded/hybrid候选策略、共享过滤、24条新合成验证问题及 `scripts/compare_retrieval.py`，默认仍为baseline，不改本地`.env`。2026-10-26隔离云端比较选择了hybrid：开发集47/47通过，新增验证集23/24通过；葡萄切分漏召回得到修复，但一个无资料的婴儿粥比例问题发生误引用，因此整体仍未通过质量门槛。比较未启用正式RAG，未连接生产索引，详情见 [召回优化状态](docs/retrieval-optimization.findings.md)。

## 日志系统

- 控制台 + `logs/` 目录下按天滚动文件日志（`app-%Y-%m-%d.log`，保留 30 天）；
- 通过 `LOG_LEVEL` 控制级别，`LOG_DIR` 控制输出目录；
- 覆盖请求处理与种子写入等关键环节。

## 约定与说明

- 代码遵循文件级/类级/函数级/参数/返回值/异常注释规范；
- JSON 列使用自定义序列化器（`ensure_ascii=False`）保证中文检索（如 `LIKE '%补铁%'`）在 MySQL 与 SQLite 下均生效；
- 生产加固已落地：Alembic 迁移替代 `create_all`（生产启动自动 `upgrade head`）、`/system/run-tests` 等调试路由仅 DEBUG 注册；部署时仍需隐藏 `/docs`（如需）并通过环境变量注入强随机 `SECRET_KEY` 与数据库凭据。

## 数据库迁移（Alembic）

数据库表结构由 Alembic 迁移链管理（配置 `backend/alembic.ini` + `backend/migrations/`），初始迁移 `0001_initial_schema` 完整创建 12 张业务表（含索引、外键 CASCADE 与 `uq_recipe_favorites_user_recipe` / `uq_meal_plans_slot` 两个唯一约束）。

`alembic.ini` 中 `sqlalchemy.url` 留空，实际连接串由 `migrations/env.py` 从 `app.core.config.settings.DATABASE_URL`（即 `.env` / 环境变量）读取注入，凭据不落仓库。

### 常用命令（在 backend/ 目录执行）

```powershell
# 升级到最新版本（幂等：已是 head 时无操作）
.\.venv\Scripts\python.exe -m alembic upgrade head

# 回滚上一个版本
.\.venv\Scripts\python.exe -m alembic downgrade -1

# 回滚到指定版本（如回到初始迁移）
.\.venv\Scripts\python.exe -m alembic downgrade 0001

# 回滚全部迁移（清空所有业务表，慎用）
.\.venv\Scripts\python.exe -m alembic downgrade base

# 查看当前版本 / 迁移历史
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic history --verbose
```

### 生成新迁移

修改 `app/models` 下 ORM 模型后，对照当前数据库自动生成增量迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe your change"
```

生成后必须人工核对 `migrations/versions/` 下的新脚本（尤其确认索引与约束），再执行 `upgrade head` 应用。注意 SQLite 对部分 ALTER 语句有限制，涉及改列/删列的迁移在 SQLite 开发库上可能需要 batch 模式，MySQL 不受影响。

### 生产启动自动迁移

- 生产模式（`DEBUG=False`）启动时，`app/main.py` 的生命周期钩子自动执行 Alembic `upgrade head`（等价于 `Base.metadata.create_all` 已在生产停用），确保表结构与迁移链一致；已是最新版本时为无操作，不会破坏存量数据；
- 开发/测试模式（`DEBUG=True`）仍保留 `create_all` 直接建表，便于快速迭代；
- 部署时需确保 `backend/alembic.ini` 与 `backend/migrations/` 目录随代码一起发布，否则生产启动会拒绝运行；
- 迁移测试见 `tests/test_migrations.py`（临时 SQLite 文件库上验证建表、唯一约束、回滚与幂等往返，可通过 `-x db_url=...` 向迁移注入自定义连接串）。
