"""
@file: app/api/v1/router.py
@description: API v1 路由聚合：将所有模块路由注册到统一路由器。
"""

from fastapi import APIRouter

from app.api.v1 import advice, advisor, auth, babies, diet, growth, notifications, recipes, users

# 汇总所有业务模块路由
# 说明：system（一键测试）路由不在此固定注册，由 app/main.py 按 settings.DEBUG 条件注册，
#       避免生产环境暴露服务端执行 pytest 的调试接口
api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(babies.router)
api_router.include_router(growth.router)
api_router.include_router(diet.router)
api_router.include_router(recipes.router)
api_router.include_router(advice.router)
api_router.include_router(advisor.router)
api_router.include_router(notifications.router)
