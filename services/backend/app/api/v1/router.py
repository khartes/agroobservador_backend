from fastapi import APIRouter

from app.api.v1.endpoints import health, imoveis, soja

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(imoveis.router, tags=["imoveis"])
api_router.include_router(soja.router, tags=["soja"])
