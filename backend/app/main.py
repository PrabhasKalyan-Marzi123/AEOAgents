from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify WordPress connectivity
    if settings.wordpress_url and settings.wordpress_app_password:
        try:
            from app.wordpress_client import wordpress_client
            wordpress_client.check_connection()
            print("WordPress connection verified")
        except Exception as e:
            print(f"Warning: WordPress connection failed: {e}")
    else:
        print("Warning: WordPress credentials not configured — running in local-only mode")
    yield


app = FastAPI(
    title="AEO Agents API",
    description="AI Visibility Engine — generates AEO-optimized content with JSON-LD structured data",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aeo-agents"}
