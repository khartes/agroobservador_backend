from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.project_name)

app.add_middleware(GZipMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["Access-Control-Allow-Origin"],
)


@app.get("/", tags=["health"])
def read_root() -> dict[str, str]:
    """Basic root endpoint that confirms the API is online."""
    return {"status": "running", "service": settings.project_name}


app.include_router(api_router, prefix=settings.api_v1_prefix)
