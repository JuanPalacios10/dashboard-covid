#!/usr/bin/env python
"""Ejecuta la ingesta del dataset de COVID-19 desde la línea de comandos.

Ejemplos::

    python scripts/ingest_dataset.py
    python scripts/ingest_dataset.py --limit-rows 20000
    python scripts/ingest_dataset.py --chunk-size 50000 --memory-limit-mb 768 --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.ingestion.memory import MemoryLimitExceeded
from app.ingestion.pipeline import (
    IngestionAlreadyRunning,
    IngestionConfig,
    IngestionError,
    OutputAlreadyExists,
    run_ingestion,
)


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Ingesta por chunks del dataset de casos positivos de COVID-19.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=settings.dataset_path,
        help="Ruta del archivo de entrada (CSV o JSON Lines).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=settings.processed_dir,
        help="Directorio donde se publica la capa procesada.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=settings.chunk_size,
        help="Filas por bloque.",
    )
    parser.add_argument(
        "--memory-limit-mb",
        type=int,
        default=settings.memory_limit_mb,
        help="Umbral máximo de RAM del proceso.",
    )
    parser.add_argument(
        "--limit-rows",
        type=int,
        default=None,
        help="Procesar solo las primeras N filas (pruebas rápidas).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reemplazar la capa procesada existente.",
    )
    parser.add_argument(
        "--no-dedupe",
        dest="deduplicate",
        action="store_false",
        default=True,
        help="No deduplicar por id_caso (la deduplicación está activa por defecto).",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Conservar el staging si la ejecución falla (depuración).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="No imprimir el progreso por chunk.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = IngestionConfig(
        source_path=args.source,
        output_dir=args.output_dir,
        chunk_size=args.chunk_size,
        memory_limit_mb=args.memory_limit_mb,
        deduplicate=args.deduplicate,
        overwrite=args.overwrite,
        limit_rows=args.limit_rows,
        keep_staging=args.keep_staging,
    )

    def on_progress(progress: dict[str, object]) -> None:
        if args.quiet:
            return
        print(
            "  chunk {chunks_procesados:>4} | leídas {filas_leidas:>10,} | "
            "válidas {filas_validas:>10,} | rechazadas {filas_rechazadas:>7,} | "
            "RAM {memoria_actual_mb:>7.1f} MB".format(**progress)
        )

    try:
        manifest = run_ingestion(config, progress_callback=on_progress)
    except (IngestionAlreadyRunning, OutputAlreadyExists, IngestionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except MemoryLimitExceeded as exc:
        print(f"Error de memoria: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Configuración inválida: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nIngesta cancelada por el usuario.", file=sys.stderr)
        return 130

    totals = manifest["totales"]
    print("\nIngesta completada")
    print(f"  run_id:           {manifest['run_id']}")
    print(f"  filas leídas:     {totals['rows_read']:,}")
    print(f"  filas válidas:    {totals['rows_clean']:,}")
    print(f"  filas rechazadas: {totals['rows_rejected']:,}")
    print(f"  duplicados:       {totals['duplicates_removed']:,}")
    print(f"  duración:         {manifest['duracion_segundos']} s")
    print(
        "  memoria pico:     "
        f"{manifest['memoria']['pico_mb']} MB "
        f"(límite {manifest['memoria']['limite_mb']} MB)"
    )
    print(f"  salida:           {manifest['salida']['directorio']}")
    print(f"  manifiesto:       {manifest.get('manifiesto')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
