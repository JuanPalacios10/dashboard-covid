"""Punto de entrada de la API del dashboard COVID-19."""

from __future__ import annotations

from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.auth import router as auth_router
from .api.dashboard import router as dashboard_router
from .api.kpis import router as kpis_router
from .api.routes import router
from .config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend del dashboard de COVID-19. Incluye la ingesta por chunks del "
        "dataset de casos positivos y la publicación de una capa Parquet limpia."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(kpis_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Expone el tiempo de procesamiento del backend para medir el SLA."""

    started = perf_counter()
    response = await call_next(request)
    elapsed_ms = (perf_counter() - started) * 1_000
    response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"
    return response


@app.get("/", tags=["sistema"])
def root() -> dict[str, str]:
    return {
        "nombre": settings.app_name,
        "version": settings.app_version,
        "documentacion": "/docs",
    }


@app.get("/health", tags=["sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}
