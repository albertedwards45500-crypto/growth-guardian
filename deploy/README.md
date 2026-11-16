# 成长宝腾讯云 Docker Compose 部署

## 目标与当前状态

目标实例：`lhins-5lekmkzn`，广州区域。用户 2026-11-16 截图显示公网 IP 为 **43.139.105.218**，实例名称为 **Windows Server–32Xj**；名称不能证明当前操作系统，必须在控制台“概览”核实。

本方案需要 **Linux Docker Engine**，适用于文档所述 Ubuntu Server 24.04，不能直接将 Linux 容器运行在 Windows Server 的 Windows 容器模式中。请先核实当前系统和登录方式；如果确为 Windows，应评估保留系统的部署方案，或在用户明确同意且完成备份后再选择重装 Ubuntu。重装不是本部署脚本的一部分。

文档内的 `43.139.5.234` 是示例地址，不能用于本实例。部署是否完成以公网冒烟测试为准，生成配置和打包本身不代表已上线。

## 资源与服务

| 服务 | 内存上限 | CPU 上限 | 公网端口 |
| --- | --- | --- | --- |
| MySQL 8.0 | 768MiB | 1.0 | 不映射 |
| FastAPI，单 worker | 512MiB | 0.9 | 不映射 |
| Nginx，前端静态站与 API 代理 | 64MiB | 0.25 | 80 |

合计内存上限 1344MiB，余量供 Linux、Docker 和文件缓存。CPU 上限不是保留核数。串行构建后端和前端，前端在本机打包以降低服务器峰值内存。数据库使用独立业务账号、128MiB buffer pool 和 40 连接上限。容器日志每个服务最多 3 × 10MB；应用文件日志保留策略沿用项目配置，应定期检查磁盘。

项目默认规则顾问可用，AI 与 RAG 默认关闭；发布包不会包含本地 `.env`、模型密钥、宝宝数据库、向量库、日志、测试或开发依赖。MySQL 命名卷永久保存服务器新增数据，后端启动自动执行 Alembic 迁移并初始化项目既有食谱和演示数据。

## 1. 服务器预检查

登录 Linux 服务器后执行：

```bash
cat /etc/os-release
uname -m
free -h
df -h /
docker version
docker compose version
docker ps --format 'table {{.Names}}\t{{.Ports}}'
ss -lnt
```

确认 Ubuntu/Linux、约 2GB 内存、有足够磁盘空间（推荐至少 8GB 空余）、Docker Engine 正常、Compose 插件 v2.20 或更新版本、80 端口没有被已有站点占用。Docker 27.5.1 可用，Compose 是单独组件，不能仅凭 Docker 版本断定已安装。

如 Docker 已安装但没有 Compose，可使用服务器软件源提供的 `docker-compose-plugin`；不要混用旧版 `docker-compose` Python 程序。对未安装 Docker 的服务器，按 Docker 官方 Ubuntu 安装说明安装 Engine 和 Compose 插件后再次检查。

确认腾讯云轻量应用服务器“防火墙”允许 TCP 80，并保留 SSH 端口。不要开放 MySQL 3306 或后端 8000。如已有站点，请使用其他 HTTP_PORT 或复用现有反向代理。

## 2. 本地构建与打包

在项目根目录的 PowerShell 中执行：

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd test
npm.cmd run build
Set-Location ..
python deploy/package_release.py
```

上传包为 `output/deploy/growth-guardian-release.tar.gz`。它包括：

```text
docker-compose.yml
backend/{Dockerfile,.dockerignore,requirements.txt,alembic.ini,app/,migrations/}
frontend/{Dockerfile,.dockerignore,nginx.conf,dist/}
deploy/{init_env.py,deploy.sh,smoke.py,package_release.py,.env.example,README.md}
```

## 3. 上传与生产配置

以下 `ubuntu` 仅为示例，替换为实际 Linux 用户；使用密码或自己已有的 SSH 私钥认证。

```powershell
scp output/deploy/growth-guardian-release.tar.gz ubuntu@43.139.105.218:~/
ssh ubuntu@43.139.105.218
```

服务器执行：

```bash
mkdir -p ~/growth-guardian
tar -xzf ~/growth-guardian-release.tar.gz -C ~/growth-guardian
cd ~/growth-guardian
python3 deploy/init_env.py http://43.139.105.218
chmod 600 .env
```

脚本仅首次生成生产 `.env`，使用随机独立数据库密码、root 密码和 96 字符 JWT 签名密钥，拒绝覆盖已有配置，不打印凭据。生产 `.env` 由 Compose 注入容器，不复制进镜像。备份时私密保存此文件，避免打印 `docker compose config` 的完整输出；校验用 `docker compose config --quiet`。

`PUBLIC_ORIGIN` 必须与实际前端地址一致；使用其他端口时例如 `http://43.139.105.218:8080`，脚本会相应设置 HTTP_PORT。`MYSQL_PASSWORD` 必须保持 URL 安全（生成的十六进制密码已满足）。不要在数据库卷初始化后单改 `.env` 中密码，MySQL 不会自动修改已存在用户的口令。

需要更换镜像仓库时，可以在 `.env` 中明确设置 `MYSQL_IMAGE`、`PYTHON_IMAGE` 和 `NGINX_IMAGE`，使用自己信任且可访问的镜像地址。Python 依赖按部署文档使用 `https://mirrors.aliyun.com/pypi/simple/`。

## 4. 构建与启动

```bash
bash deploy/deploy.sh
```

脚本先检查配置，串行构建后端与前端，再启动 MySQL → 健康检查 → 后端迁移与初始化 → Nginx，并等待所有容器健康。服务器 3Mbps 带宽下首次下载镜像及 Python 依赖可能较慢。

后端以非 root 用户运行，只有 Nginx 80 对公网映射。`DEBUG=false` 禁用调试接口，Nginx 同时隐藏 API 文档和测试静态页。Vue 路由刷新回退到 index.html，API 路径保持 `/api/v1`。

## 5. 验证与访问

从本机或其他外网环境执行：

```powershell
python deploy/smoke.py http://43.139.105.218 --demo-login
```

检查首页、登录页、SPA 深层路由、健康检查、认证保护、调试页面 404、演示登录与 MySQL 读取。脚本不创建或删除宝宝记录，不打印登录令牌。

访问地址：`http://43.139.105.218`。项目既有共享演示账号为 `13800000000 / 123456`，用于演示；个人数据请注册独立账号。部署后请在浏览器检查登录、宝宝档案、成长曲线和食谱页面。

当前配置为 HTTP。正式收集个人数据前，应准备域名并在反向代理上配置 HTTPS，不能只把 PUBLIC_ORIGIN 改为 https 就得到证书和 TLS。大陆域名网站还需完成相应备案。

## 6. 状态、维护与备份

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 db
docker stats --no-stream
docker system df
```

修改前先备份数据库；数据库密码通过容器内部环境读取，不在命令行展开：

```bash
mkdir -p backups
chmod 700 backups
docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --no-tablespaces baby_growth' > "backups/baby_growth-$(date +%Y%m%d-%H%M%S).sql"
chmod 600 backups/*.sql
```

将备份和生产 `.env` 存到私密的异机位置。恢复应先用独立数据库验证，再安排生产切换；不要直接向现有数据库导入覆盖。

临时停止：`docker compose stop`。恢复：`docker compose start`。重启后端：`docker compose restart backend`。更新：备份数据库、保留 `.env` 和命名卷、上传新包并重新运行 `bash deploy/deploy.sh`。应用迁移会自动执行，涉及数据库结构变更时，回退旧镜像前须评估迁移兼容性。

`docker compose down` 保留命名卷，但会中断服务；不要使用 `down -v`，它会删除数据库卷。

## 7. 排查

- 页面无法访问：检查公网 IP、腾讯云防火墙 TCP 80、端口占用及 `docker compose ps`。
- 502：查看 backend 的健康状态与日志，检查 MySQL 是否健康及 Alembic 迁移错误。
- 镜像下载超时：确认服务器网络和可用镜像仓库，不要反复重建已成功层。
- pip 安装失败：检查阿里云 PyPI 地址、可用磁盘、Python 版本及依赖错误；后端基础镜像为 Python 3.12 slim。
- MySQL 不健康：检查 db 日志、磁盘与内存；已有卷不能靠更换 `.env` 密码修复认证。
- 容器退出码 137 / OOM：检查 `free -h`、`docker stats`、`docker inspect`；保持单 worker，停止非必要服务，必要时升级内存。不要在 2GB 服务器上运行前端 Node 构建或额外 Qdrant 服务。
- 端口被占用：保留现有服务，调整 HTTP_PORT / PUBLIC_ORIGIN，或对接现有 Nginx。
- 文件换行错误：以 `bash deploy/deploy.sh` 启动；若上传工具转换了换行，执行 `sed -i 's/\r$//' deploy/deploy.sh`。
