"""Persistencia masiva de la capa limpia en MongoDB."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Self

import pandas as pd
from pymongo import ASCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection


class MongoWriter:
    """Escribe casos por lotes y reconstruye los agregados de consulta."""

    def __init__(
        self,
        *,
        uri: str,
        database: str,
        cases_collection: str,
        summary_collection: str,
        kpis_collection: str = "kpis_gerenciales",
        dashboard_collection: str = "dashboard_agregados",
        batch_size: int = 5_000,
    ) -> None:
        self.batch_size = batch_size
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5_000)
        self.database = self.client[database]
        self.cases: Collection[dict[str, Any]] = self.database[cases_collection]
        self.summary: Collection[dict[str, Any]] = self.database[
            summary_collection
        ]
        self.kpis: Collection[dict[str, Any]] = self.database[kpis_collection]
        self.dashboard: Collection[dict[str, Any]] = self.database[
            dashboard_collection
        ]
        self.documents_written = 0
        self.bulk_errors = 0
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.cases.create_index("id_caso", unique=True)
        self.cases.create_index(
            [("fecha_reporte_web", ASCENDING), ("codigo_divipola_municipio", ASCENDING)]
        )
        self.summary.create_index(
            [
                ("fecha", ASCENDING),
                ("codigo_divipola_municipio", ASCENDING),
            ],
            unique=True,
        )

    def reset(self) -> None:
        """Elimina las colecciones derivadas para una recarga completa."""

        self.cases.drop()
        self.summary.drop()
        self.kpis.drop()
        self.dashboard.drop()
        self._ensure_indexes()

    def check_connection(self) -> None:
        """Comprueba explícitamente que MongoDB está disponible."""

        self.client.admin.command("ping")

    def write(self, frame: pd.DataFrame) -> None:
        """Inserta o actualiza un DataFrame limpio en sublotes masivos."""

        if frame.empty:
            return

        documents = [_to_document(row) for row in frame.to_dict("records")]
        for start in range(0, len(documents), self.batch_size):
            batch = documents[start : start + self.batch_size]
            operations = [
                UpdateOne(
                    {"id_caso": document["id_caso"]},
                    {"$set": document},
                    upsert=True,
                )
                for document in batch
            ]
            result = self.cases.bulk_write(operations, ordered=False)
            self.documents_written += result.upserted_count + result.modified_count

    def insert_many(self, frame: pd.DataFrame) -> None:
        """Inserta un lote nuevo sin consultar por ``id_caso``.

        Es la ruta rápida para la carga inicial desde Parquet. Requiere que la
        colección esté vacía; para recargas idempotentes se usa ``write``.
        """

        if frame.empty:
            return

        documents = [_to_document(row) for row in frame.to_dict("records")]
        for start in range(0, len(documents), self.batch_size):
            batch = documents[start : start + self.batch_size]
            self.cases.insert_many(batch, ordered=False)
            self.documents_written += len(batch)

    def consolidate_summary(self) -> None:
        """Reconstruye los totales diarios y municipales desde casos_covid."""

        pipeline = [
            {
                "$group": {
                    "_id": {
                        "fecha": "$fecha_reporte_web",
                        "codigo_divipola_municipio": "$codigo_divipola_municipio",
                    },
                    "nombre_municipio": {"$first": "$nombre_municipio"},
                    "total_casos": {"$sum": 1},
                    "total_recuperados": {
                        "$sum": {
                            "$cond": [{"$eq": ["$recuperado", "Recuperado"]}, 1, 0]
                        }
                    },
                    "total_fallecidos": {
                        "$sum": {
                            "$cond": [{"$eq": ["$recuperado", "Fallecido"]}, 1, 0]
                        }
                    },
                    "total_activos": {
                        "$sum": {
                            "$cond": [{"$eq": ["$recuperado", "Activo"]}, 1, 0]
                        }
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "fecha": "$_id.fecha",
                    "codigo_divipola_municipio": "$_id.codigo_divipola_municipio",
                    "nombre_municipio": 1,
                    "total_casos": 1,
                    "total_recuperados": 1,
                    "total_fallecidos": 1,
                    "total_activos": 1,
                    "actualizado_en": datetime.now(UTC),
                }
            },
            {
                "$merge": {
                    "into": self.summary.name,
                    "on": ["fecha", "codigo_divipola_municipio"],
                    "whenMatched": "replace",
                    "whenNotMatched": "insert",
                }
            },
        ]
        list(self.cases.aggregate(pipeline, allowDiskUse=True))

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


def _to_document(row: dict[str, Any]) -> dict[str, Any]:
    """Convierte valores Pandas/NumPy a tipos que BSON puede serializar."""

    document: dict[str, Any] = {}
    for key, value in row.items():
        if pd.isna(value):
            document[key] = None
        elif isinstance(value, pd.Timestamp):
            document[key] = value.to_pydatetime()
        elif isinstance(value, datetime):
            document[key] = value
        elif isinstance(value, date):
            # Parquet devuelve ``datetime.date``; BSON solo serializa
            # ``datetime.datetime``. Se fija medianoche UTC.
            document[key] = datetime.combine(value, time.min, tzinfo=UTC)
        elif hasattr(value, "item"):
            document[key] = value.item()
        else:
            document[key] = value
    return document
