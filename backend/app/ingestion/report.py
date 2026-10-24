"""Generación del manifiesto JSON de cada ejecución de ingesta."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schema import FINAL_COLUMNS
from .stats import ChunkReport, summarize_reports

PIPELINE_VERSION = "1.0.0"


def new_run_id() -> str:
    """Identificador único y ordenable de la ejecución."""

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def build_manifest(
    *,
    run_id: str,
    status: str,
    source_path: Path,
    source_size_bytes: int,
    chunk_size: int,
    memory_limit_mb: int,
    deduplicate: bool,
    compression: str,
    started_at: datetime,
    finished_at: datetime,
    peak_memory_mb: float,
    reports: list[ChunkReport],
    output_dir: Path,
    rows_written: int,
    rejected_path: Path | None,
    error: str | None = None,
) -> dict[str, Any]:
    """Construye el diccionario del manifiesto (JSON serializable)."""

    summary = summarize_reports(reports)
    duration = max((finished_at - started_at).total_seconds(), 0.0)

    manifest: dict[str, Any] = {
        "version_pipeline": PIPELINE_VERSION,
        "run_id": run_id,
        "estado": status,
        "iniciado_en": started_at.isoformat(),
        "finalizado_en": finished_at.isoformat(),
        "duracion_segundos": round(duration, 2),
        "origen": {
            "ruta": str(source_path),
            "tamano_bytes": source_size_bytes,
            "tamano_mb": round(source_size_bytes / (1024 * 1024), 2),
        },
        "configuracion": {
            "chunk_size": chunk_size,
            "limite_memoria_mb": memory_limit_mb,
            "deduplicar_por_id_caso": deduplicate,
            "compresion_parquet": compression,
        },
        "memoria": {
            "pico_mb": peak_memory_mb,
            "limite_mb": memory_limit_mb,
            "dentro_del_limite": peak_memory_mb <= memory_limit_mb,
        },
        "chunks_procesados": len(reports),
        "salida": {
            "directorio": str(output_dir / "casos"),
            "rechazados": str(rejected_path) if rejected_path else None,
            "filas_escritas": rows_written,
            "columnas": list(FINAL_COLUMNS),
            "particionado_por": "anio de fecha_reporte_web",
        },
        **summary,
    }
    if error:
        manifest["error"] = error

    return manifest


def write_manifest(manifest: dict[str, Any], manifests_dir: Path) -> Path:
    """Persiste el manifiesto y devuelve su ruta."""

    manifests_dir.mkdir(parents=True, exist_ok=True)
    path = manifests_dir / f"ingesta_{manifest['run_id']}.json"
    temporary_path = path.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    os.replace(temporary_path, path)
    return path
