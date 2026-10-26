"""Orquestador de la ingesta por chunks del dataset de COVID-19."""

from __future__ import annotations

import logging
import os
import shutil
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa

try:  # pragma: no cover - depende del sistema operativo
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from .cleaner import clean_chunk
from .dedupe import IdDeduplicator
from .memory import MemoryMonitor
from .mongo_writer import MongoWriter
from .report import build_manifest, new_run_id, write_manifest
from .schema import (
    FINAL_ARROW_SCHEMA,
    FINAL_COLUMNS,
    NORMALIZED_SOURCE_TO_FINAL,
    REJECTED_ARROW_SCHEMA,
    REQUIRED_COLUMNS,
    SOURCE_TO_FINAL,
    normalize_header,
)
from .stats import ChunkReport
from .writer import ParquetPartitionWriter

ProgressCallback = Callable[[dict[str, object]], None]

logger = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    """Error base del proceso de ingesta."""


class DatasetSchemaError(IngestionError):
    """El archivo no contiene todas las columnas requeridas."""


class OutputAlreadyExists(IngestionError):
    """Ya existe una capa procesada y no se pidió sobrescribirla."""


class IngestionAlreadyRunning(IngestionError):
    """Ya hay otra ingesta en ejecución."""


@dataclass
class IngestionConfig:
    """Parámetros de una ejecución de ingesta."""

    source_path: Path
    output_dir: Path
    chunk_size: int = 100_000
    memory_limit_mb: int = 1_024
    deduplicate: bool = True
    overwrite: bool = False
    limit_rows: int | None = None
    compression: str = "zstd"
    keep_staging: bool = False
    mongo_enabled: bool = False
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_database: str = "covid_dashboard"
    mongo_cases_collection: str = "casos_covid"
    mongo_summary_collection: str = "resumen_diario_municipios"
    mongo_batch_size: int = 5_000

    def __post_init__(self) -> None:
        if self.chunk_size < 1:
            raise ValueError("chunk_size debe ser mayor que cero")
        if self.memory_limit_mb < 16:
            raise ValueError("memory_limit_mb debe ser al menos 16")
        if self.limit_rows is not None and self.limit_rows < 1:
            raise ValueError("limit_rows debe ser mayor que cero")


_PROCESS_LOCK = threading.Lock()


@contextmanager
def _ingestion_lock(output_dir: Path) -> Iterator[None]:
    """Evita dos ingestas simultáneas (mismo u otro proceso)."""

    if not _PROCESS_LOCK.acquire(blocking=False):
        raise IngestionAlreadyRunning("Ya hay una ingesta en curso en este proceso.")

    lock_path = output_dir / ".ingest.lock"
    lock_file = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("w", encoding="utf-8")
        if fcntl is not None:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise IngestionAlreadyRunning(
                    "Ya hay una ingesta en curso (lock del directorio de salida)."
                ) from exc
        yield
    finally:
        if lock_file is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
            finally:
                lock_file.close()
        _PROCESS_LOCK.release()


def resolve_source_columns(header_columns: list[str]) -> tuple[list[str], dict[str, str]]:
    """Valida el encabezado y devuelve columnas a leer y el mapeo de nombres.

    El mapeo se construye normalizando los encabezados, por lo que funciona
    aunque el archivo cambie mayúsculas, tildes o espacios en los títulos.
    """

    rename_map: dict[str, str] = {}
    for actual in header_columns:
        final = NORMALIZED_SOURCE_TO_FINAL.get(normalize_header(actual))
        if final is None:
            continue
        if final in rename_map.values():
            raise DatasetSchemaError(
                f"El archivo tiene más de una columna equivalente a '{final}'."
            )
        rename_map[actual] = final

    present = set(rename_map.values())
    missing = [column for column in REQUIRED_COLUMNS if column not in present]
    if missing:
        expected = {
            final: source
            for source, final in SOURCE_TO_FINAL.items()
            if final in missing
        }
        detail = ", ".join(f"'{source}'" for source in expected.values())
        raise DatasetSchemaError(
            "Faltan columnas obligatorias en el archivo: " + detail
        )

    # Se leen únicamente las columnas necesarias (menos I/O y menos RAM).
    return list(rename_map), rename_map


def _read_header(source_path: Path) -> list[str]:
    if source_path.suffix.lower() == ".csv":
        header = pd.read_csv(source_path, nrows=0, encoding="utf-8-sig")
    else:
        try:
            header = pd.read_json(source_path, lines=True, nrows=1)
        except ValueError as exc:
            raise IngestionError(
                "El archivo JSON debe estar en formato JSON Lines "
                "(un objeto por línea). Los arreglos JSON no se pueden "
                "leer por chunks sin cargar todo el archivo."
            ) from exc
    return [str(column) for column in header.columns]


def _iter_chunks(
    source_path: Path,
    usecols: list[str],
    chunk_size: int,
) -> Iterator[pd.DataFrame]:
    """Itera el archivo en bloques, sin cargarlo completo en memoria.

    Para CSV se leen únicamente las columnas necesarias. Para JSON Lines no
    existe ``usecols`` en Pandas, así que se seleccionan después de leer el
    bloque.
    """

    if source_path.suffix.lower() == ".csv":
        yield from pd.read_csv(
            source_path,
            usecols=usecols,
            dtype=str,
            chunksize=chunk_size,
            encoding="utf-8-sig",
            on_bad_lines="warn",
        )
        return

    yield from pd.read_json(
        source_path,
        lines=True,
        chunksize=chunk_size,
        dtype=False,
    )


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def run_ingestion(
    config: IngestionConfig,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """Ejecuta la ingesta completa y devuelve el manifiesto generado.

    La escritura se hace primero en un directorio de staging y, solo si todo
    termina bien, se publica en ``output_dir``. Así un fallo no deja una capa
    procesada incompleta visible para el resto del sistema.
    """

    source_path = Path(config.source_path).expanduser().resolve()
    output_dir = Path(config.output_dir).expanduser().resolve()

    if not source_path.is_file():
        raise IngestionError(f"No existe el archivo de datos: {source_path}")
    if source_path.suffix.lower() not in {".csv", ".json", ".jsonl", ".ndjson"}:
        raise IngestionError(
            "La ingesta soporta archivos .csv o JSON Lines (.json/.jsonl/.ndjson). "
            f"Extensión recibida: '{source_path.suffix}'."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    with _ingestion_lock(output_dir):
        final_cases_dir = output_dir / "casos"
        final_rejected_dir = output_dir / "rechazados"

        if final_cases_dir.exists() and not config.overwrite:
            raise OutputAlreadyExists(
                f"Ya existe '{final_cases_dir}'. Use --overwrite para reemplazarlo."
            )

        run_id = new_run_id()
        staging_dir = output_dir / f".staging-{run_id}"
        staging_cases = staging_dir / "casos"
        staging_rejected = staging_dir / "rechazados"
        staging_cases.mkdir(parents=True, exist_ok=True)

        started_at = datetime.now(UTC)
        source_size = source_path.stat().st_size
        reports: list[ChunkReport] = []
        deduplicator = IdDeduplicator() if config.deduplicate else None
        monitor = MemoryMonitor(config.memory_limit_mb)
        mongo_writer = (
            MongoWriter(
                uri=config.mongo_uri,
                database=config.mongo_database,
                cases_collection=config.mongo_cases_collection,
                summary_collection=config.mongo_summary_collection,
                batch_size=config.mongo_batch_size,
            )
            if config.mongo_enabled
            else None
        )
        cleanup_writers: list[ParquetPartitionWriter] = []

        cases_writer = ParquetPartitionWriter(
            staging_cases,
            FINAL_ARROW_SCHEMA,
            compression=config.compression,
            row_group_size=config.chunk_size,
        )
        rejected_writer = ParquetPartitionWriter(
            staging_rejected,
            REJECTED_ARROW_SCHEMA,
            filename="rechazados.parquet",
            compression=config.compression,
            row_group_size=config.chunk_size,
        )
        cleanup_writers.extend([cases_writer, rejected_writer])

        total_read = 0
        total_clean = 0
        total_rejected = 0
        chunks_processed = 0

        monitor.start()
        try:
            if mongo_writer is not None:
                mongo_writer.check_connection()

            header_columns = _read_header(source_path)
            usecols, rename_map = resolve_source_columns(header_columns)
            internal_order = list(FINAL_COLUMNS) + ["_unidad_edad"]

            for raw_chunk in _iter_chunks(
                source_path, usecols, config.chunk_size
            ):
                if config.limit_rows is not None:
                    remaining = config.limit_rows - total_read
                    if remaining <= 0:
                        break
                    if len(raw_chunk) > remaining:
                        raw_chunk = raw_chunk.iloc[:remaining].copy()

                if raw_chunk.empty:
                    break

                total_read += len(raw_chunk)
                chunks_processed += 1

                monitor.check()

                mapped = raw_chunk.rename(columns=rename_map)
                mapped = mapped.loc[:, internal_order]

                clean, rejected, report = clean_chunk(
                    mapped, deduplicator=deduplicator
                )
                reports.append(report)

                if not clean.empty:
                    if mongo_writer is not None:
                        mongo_writer.write(clean)
                    years = clean["fecha_reporte_web"].dt.year.astype("int16")
                    for year, group in clean.groupby(years, sort=True):
                        cases_writer.write(group, partition=int(year))

                if not rejected.empty:
                    rejected = rejected.copy()
                    rejected["anio_reporte"] = (
                        rejected["fecha_reporte_web"].dt.year.astype("Int16")
                    )
                    rejected_writer.write(rejected, partition=None)

                total_clean += len(clean)
                total_rejected += len(rejected)

                if progress_callback is not None:
                    progress_callback(
                        {
                            "run_id": run_id,
                            "chunks_procesados": chunks_processed,
                            "filas_leidas": total_read,
                            "filas_validas": total_clean,
                            "filas_rechazadas": total_rejected,
                            "memoria_actual_mb": monitor.current_mb,
                            "memoria_pico_mb": monitor.peak_mb,
                        }
                    )

                monitor.check()

                # Los buffers de Arrow/Pandas quedan retenidos por el
                # allocator entre chunks; liberarlos mantiene estable el RSS.
                pa.default_memory_pool().release_unused()

            monitor.stop()

            if cases_writer.rows_written != total_clean:
                raise IngestionError(
                    "Inconsistencia interna: filas válidas "
                    f"({total_clean}) != filas escritas ({cases_writer.rows_written})."
                )

            cases_writer.close()
            rejected_writer.close()
            cleanup_writers.clear()

            if mongo_writer is not None:
                mongo_writer.consolidate_summary()

            rejected_path: Path | None = None
            if rejected_writer.rows_written > 0:
                rejected_path = final_rejected_dir

            _publish(
                staging_cases=staging_cases,
                staging_rejected=staging_rejected,
                final_cases=final_cases_dir,
                final_rejected=final_rejected_dir,
                overwrite=config.overwrite,
                has_rejected=rejected_writer.rows_written > 0,
            )

            finished_at = datetime.now(UTC)
            manifest = build_manifest(
                run_id=run_id,
                status="completado",
                source_path=source_path,
                source_size_bytes=source_size,
                chunk_size=config.chunk_size,
                memory_limit_mb=config.memory_limit_mb,
                deduplicate=config.deduplicate,
                compression=config.compression,
                started_at=started_at,
                finished_at=finished_at,
                peak_memory_mb=monitor.peak_mb,
                reports=reports,
                output_dir=output_dir,
                rows_written=cases_writer.rows_written,
                rejected_path=rejected_path,
            )
            manifest_path = write_manifest(manifest, output_dir / "manifests")
            manifest["manifiesto"] = str(manifest_path)
            return manifest

        except Exception as exc:
            finished_at = datetime.now(UTC)
            try:
                monitor.stop()
            except Exception:
                logger.warning(
                    "No se pudo detener el monitor de memoria.", exc_info=True
                )

            failure_manifest = build_manifest(
                run_id=run_id,
                status="fallido",
                source_path=source_path,
                source_size_bytes=source_size,
                chunk_size=config.chunk_size,
                memory_limit_mb=config.memory_limit_mb,
                deduplicate=config.deduplicate,
                compression=config.compression,
                started_at=started_at,
                finished_at=finished_at,
                peak_memory_mb=monitor.peak_mb,
                reports=reports,
                output_dir=output_dir,
                rows_written=0,
                rejected_path=None,
                error=f"{type(exc).__name__}: {exc}",
            )
            write_manifest(failure_manifest, output_dir / "manifests")
            raise

        finally:
            for writer in cleanup_writers:
                try:
                    writer.close()
                except Exception:
                    logger.warning(
                        "No se pudo cerrar un writer Parquet.", exc_info=True
                    )
            if mongo_writer is not None:
                mongo_writer.close()
            if not config.keep_staging:
                shutil.rmtree(staging_dir, ignore_errors=True)


def _publish(
    *,
    staging_cases: Path,
    staging_rejected: Path,
    final_cases: Path,
    final_rejected: Path,
    overwrite: bool,
    has_rejected: bool,
) -> None:
    """Publica el staging en su ubicación definitiva de forma atómica por carpeta."""

    if final_cases.exists():
        if not overwrite:
            raise OutputAlreadyExists(
                f"Ya existe '{final_cases}'. Use --overwrite para reemplazarlo."
            )
        shutil.rmtree(final_cases)

    os.replace(staging_cases, final_cases)

    if final_rejected.exists():
        shutil.rmtree(final_rejected)
    if has_rejected:
        os.replace(staging_rejected, final_rejected)
