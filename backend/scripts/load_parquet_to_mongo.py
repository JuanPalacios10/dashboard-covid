#!/usr/bin/env python
"""Carga la capa Parquet procesada en MongoDB y consolida el tablero.

Ejemplos::

    # Carga completa desde data/processed/casos y consolida agregados
    python scripts/load_parquet_to_mongo.py

    # Recarga limpiando las colecciones derivadas
    python scripts/load_parquet_to_mongo.py --reset

    # Solo recalcular agregados del tablero desde Parquet
    python scripts/load_parquet_to_mongo.py --skip-load

    # Incluir también el resumen diario por municipio
    python scripts/load_parquet_to_mongo.py --with-summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow.parquet as pq

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.ingestion.dashboard_aggregates import (
    consolidate_dashboard_from_parquet,
)
from app.ingestion.mongo_writer import MongoWriter
from app.ingestion.schema import FINAL_COLUMNS


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Carga Parquet a MongoDB y consolida agregados del tablero.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        default=settings.processed_dir / "casos",
        help="Directorio con particiones anio=AAAA/casos.parquet.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.mongo_batch_size,
        help="Documentos por lote de escritura.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Elimina casos, resumen, KPIs y agregados antes de cargar.",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="No carga casos en MongoDB; solo recalcula los agregados desde Parquet.",
    )
    parser.add_argument(
        "--upsert",
        action="store_true",
        help=(
            "Actualiza por id_caso en lugar de insertar. Más lento, pero "
            "idempotente sobre una colección ya cargada."
        ),
    )
    parser.add_argument(
        "--with-summary",
        action="store_true",
        help="Reconstruye también el resumen diario por municipio.",
    )
    return parser.parse_args()


def _parquet_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("anio=*/casos.parquet"))
    if not files:
        files = sorted(directory.glob("*.parquet"))
    return files


def main() -> int:
    settings = get_settings()
    args = parse_args()

    if args.reset and args.skip_load:
        print(
            "Error: --reset y --skip-load no se pueden usar juntos.",
            file=sys.stderr,
        )
        return 2

    files = _parquet_files(args.parquet_dir)
    if not files:
        print(
            f"Error: no se encontraron archivos Parquet en {args.parquet_dir}",
            file=sys.stderr,
        )
        return 1

    writer = MongoWriter(
        uri=settings.mongo_uri,
        database=settings.mongo_database,
        cases_collection=settings.mongo_cases_collection,
        summary_collection=settings.mongo_summary_collection,
        kpis_collection=settings.mongo_kpis_collection,
        dashboard_collection=settings.mongo_dashboard_collection,
        batch_size=args.batch_size,
    )

    try:
        writer.check_connection()
        print(
            f"MongoDB conectado: {settings.mongo_uri} / "
            f"{settings.mongo_database}"
        )

        if args.reset:
            print("Eliminando colecciones derivadas...")
            writer.reset()
        elif not args.skip_load and not args.upsert:
            existing = writer.cases.estimated_document_count()
            if existing:
                print(
                    "Error: la colección de casos ya tiene documentos. "
                    "Use --reset para recargar desde cero o --upsert para "
                    "actualizar por id_caso.",
                    file=sys.stderr,
                )
                return 2

        total = 0
        if not args.skip_load:
            for file in files:
                parquet = pq.ParquetFile(file)
                print(f"Leyendo {file} ({parquet.metadata.num_rows:,} filas)")
                for batch in parquet.iter_batches(
                    batch_size=args.batch_size,
                    columns=list(FINAL_COLUMNS),
                ):
                    frame = batch.to_pandas()
                    if args.upsert:
                        writer.write(frame)
                    else:
                        writer.insert_many(frame)
                    total += len(frame)
                    print(
                        f"\r  cargados {total:,} documentos",
                        end="",
                        flush=True,
                    )
            print()
            print(f"Carga finalizada: {total:,} filas procesadas.")

        if args.with_summary:
            print("Consolidando resumen diario por municipio...")
            writer.consolidate_summary()
            print("Resumen diario consolidado.")

        print("Consolidando agregados del tablero desde Parquet...")
        summary = consolidate_dashboard_from_parquet(
            args.parquet_dir,
            writer.dashboard,
            writer.kpis,
        )
        print(
            "Tablero consolidado: "
            f"confirmados={summary['confirmados']:,} | "
            f"fallecidos={summary['fallecidos']:,} | "
            f"recuperados={summary['recuperados']:,} | "
            f"activos={summary['activos']:,} | "
            f"fecha_corte={summary['fecha_corte']} | "
            f"documentos={summary['series'] + summary['territorios'] + summary['demografia'] + summary['heatmap']}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - reportar cualquier fallo de carga
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        writer.close()


if __name__ == "__main__":
    raise SystemExit(main())
