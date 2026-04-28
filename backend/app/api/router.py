from fastapi import APIRouter
from app.api.content import router as content_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(content_router)
