"""Persistencia masiva de la capa limpia en MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from pymongo import ASCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection


class MongoWriter:
    """Escribe casos por lotes y reconstruye el resumen diario por municipio."""

    def __init__(
        self,
        *,
        uri: str,
        database: str,
        cases_collection: str,
        summary_collection: str,
        batch_size: int = 5_000,
    ) -> None:
        self.batch_size = batch_size
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5_000)
        self.database = self.client[database]
        self.cases: Collection[dict[str, Any]] = self.database[cases_collection]
        self.summary: Collection[dict[str, Any]] = self.database[
            summary_collection
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
                    "actualizado_en": datetime.now(timezone.utc),
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

    def __enter__(self) -> MongoWriter:
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
        elif hasattr(value, "item"):
            document[key] = value.item()
        else:
            document[key] = value
    return document
