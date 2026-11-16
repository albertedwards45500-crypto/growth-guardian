# 成长宝（Growth Guardian）

面向家庭的宝宝成长记录与辅食助手，支持宝宝档案、成长曲线、饮食记录、辅食食谱、通知及成长顾问。

## 项目结构

- `frontend/`：Vue 3、TypeScript、Vite、Pinia 前端，包含单元测试。
- `backend/`：FastAPI、SQLAlchemy、MySQL 后端，包含数据库迁移、测试及智能顾问与知识检索功能。
- `stitch_/`：界面设计参考。
- 根目录的项目介绍、立项文档及设计书：项目说明材料。

## 本地运行

需要 Python 3.10+、Node.js/npm 和 MySQL 8.0。

### 后端

在 PowerShell 中执行：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `backend/.env`，填写自己的数据库连接与随机生成的 `SECRET_KEY`。本地开发可设置 `DEBUG=true`；生产环境使用 `DEBUG=false` 并配置真实部署参数。智能顾问和知识检索默认关闭，可按需配置，详见 [顾问说明](backend/docs/advisor.md)。

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8300
```

接口文档：<http://127.0.0.1:8300/docs>。

### 前端

另开 PowerShell：

```powershell
cd frontend
npm ci
npm run dev
```

访问 <http://localhost:5173>。默认开发代理连接后端 `8300` 端口。完成首次配置后，也可使用根目录的 `启动成长宝.bat` 启动。

## 验证

```powershell
# 后端：在 backend 目录执行
.\.venv\Scripts\python.exe -m pytest -c pytest.ini -q

# 前端：在 frontend 目录执行
npm test
npm run build
```

更多说明见 [后端文档](backend/README.md) 和 [前端文档](frontend/README.md)。仓库保留 `.env.example` 配置示例；本地密钥、依赖、运行数据与临时文件已通过 `.gitignore` 排除。

## 腾讯云部署

Docker Compose 配置及操作步骤见 [部署说明](deploy/README.md)。前端在本机构建，服务器运行 Nginx、FastAPI 与 MySQL，适配 2 核 2GB 的 Linux 实例。部署前必须核实服务器操作系统；Windows Server 不能直接使用此 Linux 容器方案。
