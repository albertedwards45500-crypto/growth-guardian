"""
@file: app/main.py
@description: FastAPI 应用入口：初始化配置、注册路由、异常处理器、CORS 与中间件，
             并支持启动时自动建表与种子数据初始化（开发环境）。
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging

# 初始化日志
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期钩子：启动时初始化数据库结构与种子数据。

    数据库结构初始化按模式分流（审计缺陷 D05）：
    - 生产模式（DEBUG=False）：执行 Alembic `upgrade head`，表结构由迁移链管理，
      版本可审计、可回滚（幂等：库结构已是最新时为无操作，不破坏存量数据）；
    - 开发/测试模式（DEBUG=True）：保留 `Base.metadata.create_all` 直接按模型建表，
      免去每次改模型后生成迁移的开发负担。

    @param app: FastAPI 应用实例
    @yield: 应用运行期
    """
    from app.core.database import Base, engine
    from app.seed.init_seed import seed_all  # noqa: F401  确保模型已导入

    if settings.DEBUG:
        # 开发/测试环境：直接按模型元数据建表，便于快速迭代
        Base.metadata.create_all(bind=engine)
    else:
        # 生产环境：通过 Alembic 迁移升级到最新版本（替代 create_all，保证结构可审计）
        _run_migrations_to_head()
    seed_all()
    yield


def _run_migrations_to_head() -> None:
    """执行 Alembic 迁移升级至最新版本（生产启动用）。

    通过 alembic.command API 在进程内执行 `upgrade head`；alembic.ini 中
    sqlalchemy.url 留空，真实连接串经 config.attributes 注入 env.py，
    避免数据库凭据写入仓库。

    @return: 无返回值
    @raises RuntimeError: alembic.ini 缺失或迁移执行失败时抛出，阻止服务带病启动
    """
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    from app.core.config import BASE_DIR

    alembic_ini = BASE_DIR / "alembic.ini"
    if not alembic_ini.is_file():
        raise RuntimeError(
            "生产启动需要 Alembic 迁移配置，但未找到 alembic.ini，"
            "请确认部署包含 backend/alembic.ini 与 backend/migrations/ 目录"
        )
    alembic_cfg = AlembicConfig(str(alembic_ini))
    # 显式以绝对路径指定迁移脚本目录，避免受启动时工作目录影响
    alembic_cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    # 注入真实数据库连接 URL（env.py 优先读取该注入值，其次回落 settings.DATABASE_URL）
    alembic_cfg.attributes["db_url"] = settings.DATABASE_URL
    alembic_command.upgrade(alembic_cfg, "head")


def register_debug_routes(target_app: FastAPI, debug: bool | None = None) -> None:
    """按 DEBUG 开关注册仅调试环境可用的路由（系统工具：一键测试等）。

    @param target_app: 目标 FastAPI 应用实例
    @param debug: 是否注册调试路由；传 None 时取全局配置 settings.DEBUG（便于测试注入覆盖）
    @return: 无返回值，副作用为向应用注册 system 路由
    """
    if debug is None:
        debug = settings.DEBUG
    if debug:
        # 延迟导入：非 DEBUG 环境不加载 pytest 执行器相关模块
        from app.api.v1.system import router as system_router

        target_app.include_router(system_router, prefix=settings.API_PREFIX)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    创建前执行生产配置安全校验：DEBUG=False 时 SECRET_KEY / DATABASE_URL
    不达标会直接拒绝启动，防止弱凭据进入生产。

    @return: 配置完成的 FastAPI 实例
    @raises RuntimeError: 生产配置校验失败时抛出（透传自 validate_production_config）
    """
    # 生产配置强校验：DEBUG=True（开发/测试）时方法内部仅告警，不中断启动
    settings.validate_production_config()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="宝宝辅食与成长记录软件后端 API（响应式 Web 应用）",
        lifespan=lifespan,
    )

    # CORS 跨域配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def unify_response_middleware(request, call_next):
        """统一成功响应的 JSON 结构为 {code, message, data}。

        业务错误（含 code 字段）不重复包装；仅包装业务 API 下的成功 JSON 响应。

        @param request: 请求对象
        @param call_next: 下一个中间件/路由处理
        @return: 统一格式的响应
        """
        response = await call_next(request)
        path = request.url.path
        content_type = response.headers.get("content-type", "")
        if not path.startswith(settings.API_PREFIX) or not content_type.startswith(
            "application/json"
        ):
            return response

        # 读取响应体（body 可能是惰性流，需遍历 body_iterator）
        try:
            body = b"".join([chunk async for chunk in response.body_iterator])
        except (RuntimeError, AttributeError):
            return response

        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-encoding")
        }
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            # 非 JSON 内容，按原样重放
            return Response(content=body, status_code=response.status_code, headers=headers)

        if isinstance(data, dict) and "code" in data:
            # 已是统一格式（业务错误等）
            return Response(content=body, status_code=response.status_code, headers=headers)

        payload = {"code": 0, "message": "ok", "data": data}
        return JSONResponse(status_code=response.status_code, content=payload, headers=headers)

    # 注册全局异常处理器
    register_exception_handlers(app)

    # 注册业务路由
    app.include_router(api_router, prefix=settings.API_PREFIX)

    # 调试路由仅在 DEBUG 模式注册（生产环境不暴露 /system/run-tests 等接口）
    register_debug_routes(app)

    # 挂载静态资源（如测试控制台页面）
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health", tags=["系统"], summary="健康检查")
    def health_check() -> dict:
        """健康检查接口，用于探活与监控。

        @return: 服务状态
        """
        return {"status": "ok", "service": settings.APP_NAME}

    return app


# 模块级应用实例，供 uvicorn 直接引用
app = create_app()
