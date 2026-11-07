"""Servicio del tablero preagregado: KPIs, series, territorio y demografía."""

from __future__ import annotations

from typing import Any, Protocol

from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from ..config import get_settings
from ..database import DatabaseError, get_mongo_db
from .kpis import KpiService, get_kpi_service


class DashboardNotFoundError(Exception):
    """No existe alguno de los documentos preagregados del tablero."""


class DepartamentoNotFoundError(Exception):
    """El código de departamento no existe en el dataset."""


class DashboardRepositoryProtocol(Protocol):
    """Contrato del repositorio de agregados del tablero."""

    def get(self, doc_id: str) -> dict[str, Any] | None:
        """Devuelve un documento por ``_id`` o ``None``."""
        ...


class DashboardRepository:
    """Repositorio de solo lectura sobre ``dashboard_agregados``."""

    def __init__(
        self,
        collection: Collection[dict[str, Any]] | None = None,
    ) -> None:
        if collection is not None:
            self.collection = collection
        else:
            settings = get_settings()
            self.collection = get_mongo_db()[settings.mongo_dashboard_collection]

    def get(self, doc_id: str) -> dict[str, Any] | None:
        try:
            document = self.collection.find_one({"_id": doc_id})
        except PyMongoError as exc:
            raise DatabaseError(
                "No fue posible consultar los agregados del tablero."
            ) from exc
        return dict(document) if document is not None else None


def _normalize_departamento(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.isdigit():
        return normalized.zfill(2)
    return normalized


class DashboardService:
    """Compone la respuesta del tablero a partir de documentos preagregados."""

    def __init__(
        self,
        repository: DashboardRepositoryProtocol | None = None,
        kpi_service: KpiService | None = None,
    ) -> None:
        self.repository = repository or DashboardRepository()
        self.kpi_service = kpi_service or get_kpi_service()

    def get(
        self,
        periodo: str | None = None,
        departamento: str | None = None,
    ) -> dict[str, Any]:
        normalized_periodo = self.kpi_service.normalize_periodo(periodo)
        normalized_departamento = _normalize_departamento(departamento)

        kpi_document = self.kpi_service.get(normalized_periodo)
        territorios = self.repository.get(
            f"territorios:{normalized_periodo}"
        )
        demografia = self.repository.get(
            f"demografia:{normalized_periodo}"
        )
        heatmap = self.repository.get(f"heatmap:{normalized_periodo}")

        if normalized_departamento:
            series = self.repository.get(
                "series:departamento:"
                f"{normalized_departamento}:{normalized_periodo}"
            )
            if series is None and territorios is not None:
                known = {
                    str(item.get("codigo"))
                    for item in territorios.get("departamentos", [])
                }
                if normalized_departamento not in known:
                    raise DepartamentoNotFoundError(
                        "El departamento solicitado no existe en el dataset."
                    )
        else:
            series = self.repository.get(
                f"series:nacional:{normalized_periodo}"
            )

        missing = [
            name
            for name, document in (
                ("series", series),
                ("territorios", territorios),
                ("demografia", demografia),
                ("heatmap", heatmap),
            )
            if document is None
        ]
        if missing:
            raise DashboardNotFoundError(
                "Faltan agregados del tablero para el período "
                f"'{normalized_periodo}': {', '.join(missing)}. "
                "Ejecute la consolidación del tablero."
            )

        return {
            "periodo": str(
                kpi_document.get(
                    "periodo",
                    "anual"
                    if normalized_periodo.isdigit()
                    else "acumulado",
                )
            ),
            "anio": (
                int(normalized_periodo)
                if normalized_periodo.isdigit()
                else None
            ),
            "fecha_corte": kpi_document["fecha_corte"],
            "actualizado_en": kpi_document["actualizado_en"],
            "kpis": {
                "casos_confirmados": kpi_document["casos_confirmados"],
                "fallecidos": kpi_document["fallecidos"],
                "recuperados": kpi_document["recuperados"],
                "activos": kpi_document["activos"],
                "tasa_letalidad": kpi_document["tasa_letalidad"],
                "tasa_recuperacion": kpi_document["tasa_recuperacion"],
            },
            "series": series,
            "territorios": territorios,
            "demografia": demografia,
            "heatmap": heatmap,
        }


def get_dashboard_service() -> DashboardService:
    """Proveedor de dependencia para FastAPI."""

    return DashboardService()
