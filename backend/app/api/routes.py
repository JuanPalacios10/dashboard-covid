"""Endpoints HTTP de la ingesta."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..config import get_settings
from ..ingestion.pipeline import (
    IngestionAlreadyRunning,
    IngestionConfig,
    OutputAlreadyExists,
)
from ..services.jobs import IngestionJobManager

router = APIRouter()
job_manager = IngestionJobManager()


class IngestaRequest(BaseModel):
    """Parámetros opcionales para lanzar la ingesta."""

    chunk_size: int | None = Field(
        default=None,
        ge=1_000,
        le=1_000_000,
        description="Filas por bloque. Si se omite se usa COVID_CHUNK_SIZE.",
    )
    memory_limit_mb: int | None = Field(
        default=None,
        ge=128,
        description="Umbral máximo de RAM. Si se omite se usa COVID_MEMORY_LIMIT_MB.",
    )
    overwrite: bool = Field(
        default=False,
        description="Reemplazar la capa procesada si ya existe.",
    )
    limit_rows: int | None = Field(
        default=None,
        ge=1,
        description="Procesar solo las primeras N filas (útil para pruebas).",
    )


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": manifest.get("run_id"),
        "estado": manifest.get("estado"),
        "finalizado_en": manifest.get("finalizado_en"),
        "duracion_segundos": manifest.get("duracion_segundos"),
        "totales": manifest.get("totales"),
        "memoria": manifest.get("memoria"),
        "salida": manifest.get("salida"),
        "error": manifest.get("error"),
    }


@router.post(
    "/ingesta",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Lanza la ingesta del dataset por chunks",
)
def start_ingestion(payload: IngestaRequest) -> dict[str, Any]:
    settings = get_settings()
    config = IngestionConfig(
        source_path=settings.dataset_path,
        output_dir=settings.processed_dir,
        chunk_size=payload.chunk_size or settings.chunk_size,
        memory_limit_mb=payload.memory_limit_mb or settings.memory_limit_mb,
        deduplicate=settings.deduplicate,
        overwrite=payload.overwrite,
        limit_rows=payload.limit_rows,
        compression=settings.parquet_compression,
        mongo_enabled=settings.mongo_enabled,
        mongo_uri=settings.mongo_uri,
        mongo_database=settings.mongo_database,
        mongo_cases_collection=settings.mongo_cases_collection,
        mongo_summary_collection=settings.mongo_summary_collection,
        mongo_batch_size=settings.mongo_batch_size,
    )

    try:
        if (settings.processed_dir / "casos").exists() and not payload.overwrite:
            raise OutputAlreadyExists(
                "Ya existe la capa procesada. Envíe overwrite=true para reemplazarla."
            )
        job = job_manager.start(config)
    except IngestionAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OutputAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "mensaje": "Ingesta iniciada en segundo plano. Consulte /api/v1/ingesta/estado.",
        "job": job,
    }


@router.get(
    "/ingesta/estado",
    summary="Estado del job de ingesta en curso o del último ejecutado",
)
def ingestion_status() -> dict[str, Any]:
    settings = get_settings()
    state = job_manager.status()

    manifests = sorted(
        (settings.processed_dir / "manifests").glob("ingesta_*.json"),
        reverse=True,
    )
    latest = _read_manifest(manifests[0]) if manifests else None
    return {
        "job": state,
        "ultima_ingesta": _manifest_summary(latest) if latest else None,
    }


@router.get(
    "/ingesta/manifiestos",
    summary="Lista los manifiestos de ingesta más recientes",
)
def list_manifests(
    limite: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    settings = get_settings()
    paths = sorted(
        (settings.processed_dir / "manifests").glob("ingesta_*.json"),
        reverse=True,
    )[:limite]

    items = []
    for path in paths:
        manifest = _read_manifest(path)
        if manifest is not None:
            items.append(_manifest_summary(manifest))

    return {"total": len(items), "manifiestos": items}
