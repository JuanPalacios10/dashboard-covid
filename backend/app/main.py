"""Punto de entrada de la API del dashboard COVID-19."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.auth import router as auth_router
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
