"""Consulta de indicadores gerenciales preagregados en MongoDB."""

from __future__ import annotations

from typing import Any, Protocol

from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from ..config import get_settings
from ..database import DatabaseError, get_mongo_db

PERIODOS_VALIDOS = frozenset({"acumulado", "2020", "2021", "2022", "2023", "2024"})


class KpiNotFoundError(Exception):
    """No existe el documento preagregado de KPIs."""


class PeriodoInvalidoError(ValueError):
    """El período solicitado no hace parte del dataset."""


class KpiRepositoryProtocol(Protocol):
    """Contrato del repositorio de KPIs para facilitar pruebas."""

    def get(self, doc_id: str) -> dict[str, Any] | None:
        """Devuelve el documento de KPIs o ``None``."""
        ...


class KpiRepository:
    """Repositorio de solo lectura sobre la colección preagregada."""

    def __init__(
        self,
        collection: Collection[dict[str, Any]] | None = None,
    ) -> None:
        if collection is not None:
            self.collection = collection
        else:
            settings = get_settings()
            self.collection = get_mongo_db()[settings.mongo_kpis_collection]

    def get(self, doc_id: str) -> dict[str, Any] | None:
        try:
            document = self.collection.find_one({"_id": doc_id})
        except PyMongoError as exc:
            raise DatabaseError(
                "No fue posible consultar los indicadores gerenciales."
            ) from exc
        return dict(document) if document is not None else None


class KpiService:
    """Servicio de indicadores gerenciales."""

    def __init__(
        self,
        repository: KpiRepositoryProtocol | None = None,
    ) -> None:
        self.repository = repository or KpiRepository()

    @staticmethod
    def normalize_periodo(periodo: str | None) -> str:
        value = (periodo or "acumulado").strip().lower()
        if value in {"", "acumulado", "nacional", "todos"}:
            return "acumulado"
        if value in PERIODOS_VALIDOS:
            return value
        raise PeriodoInvalidoError(
            "El período debe ser 'acumulado' o un año entre 2020 y 2024."
        )

    @staticmethod
    def doc_id(periodo: str) -> str:
        return "nacional" if periodo == "acumulado" else periodo

    def get(self, periodo: str | None = None) -> dict[str, Any]:
        normalized = self.normalize_periodo(periodo)
        document = self.repository.get(self.doc_id(normalized))
        if document is None:
            raise KpiNotFoundError(
                "Los indicadores gerenciales aún no están disponibles para "
                f"el período '{normalized}'. Ejecute la consolidación del tablero."
            )
        return document

    def get_national(self) -> dict[str, Any]:
        """Compatibilidad con la primera versión del endpoint."""

        return self.get("acumulado")


def get_kpi_service() -> KpiService:
    """Proveedor de dependencia para FastAPI."""

    return KpiService()
