"""Endpoints de indicadores gerenciales."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ..database import DatabaseError
from ..services.auth import UserRole
from ..services.kpis import (
    KpiNotFoundError,
    KpiService,
    PeriodoInvalidoError,
    get_kpi_service,
)
from .auth import require_roles

router = APIRouter(prefix="/kpis", tags=["indicadores"])


class KpiValores(BaseModel):
    """Métricas principales de la vista gerencial."""

    casos_confirmados: int = Field(ge=0)
    fallecidos: int = Field(ge=0)
    recuperados: int = Field(ge=0)
    activos: int = Field(ge=0)
    tasa_letalidad: float = Field(ge=0, le=1)
    tasa_recuperacion: float = Field(ge=0, le=1)


class KpiMeta(BaseModel):
    """Metadatos de trazabilidad del documento preagregado."""

    fuente: str
    version_esquema: int


class KpiResponse(BaseModel):
    """Respuesta de KPIs gerenciales nacionales."""

    scope: str
    periodo: str
    anio: int | None
    fecha_corte: date
    actualizado_en: datetime
    kpis: KpiValores
    meta: KpiMeta


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"Fecha no válida: {value!r}")


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    raise ValueError(f"Fecha/hora no válida: {value!r}")


def _to_response(document: dict[str, Any]) -> KpiResponse:
    try:
        valores = KpiValores(
            casos_confirmados=int(document["casos_confirmados"]),
            fallecidos=int(document["fallecidos"]),
            recuperados=int(document["recuperados"]),
            activos=int(document["activos"]),
            tasa_letalidad=float(document["tasa_letalidad"]),
            tasa_recuperacion=float(document["tasa_recuperacion"]),
        )
        meta = KpiMeta(
            fuente=str(document.get("fuente", "kpis_gerenciales")),
            version_esquema=int(document.get("version_esquema", 2)),
        )
        return KpiResponse(
            scope=str(document.get("scope", "nacional")),
            periodo=str(document.get("periodo", "acumulado")),
            anio=(
                int(document["anio"])
                if document.get("anio") is not None
                else None
            ),
            fecha_corte=_coerce_date(document["fecha_corte"]),
            actualizado_en=_coerce_datetime(document["actualizado_en"]),
            kpis=valores,
            meta=meta,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El documento de indicadores está incompleto o es inválido. "
                "Vuelva a ejecutar la consolidación del tablero."
            ),
        ) from exc


@router.get(
    "/gerenciales",
    response_model=KpiResponse,
    status_code=status.HTTP_200_OK,
    summary="Indicadores gerenciales nacionales",
    description=(
        "Devuelve los KPIs nacionales desde la colección preagregada "
        "``kpis_gerenciales``. Acepta ``anio=acumulado`` o un año entre "
        "2020 y 2024. No consulta la colección de casos individuales."
    ),
)
def get_gerencial_kpis(
    response: Response,
    _current_user: Annotated[
        dict[str, Any],
        Depends(
            require_roles(
                [UserRole.ADMIN, UserRole.ANALISTA, UserRole.EJECUTIVO]
            )
        ),
    ],
    service: Annotated[KpiService, Depends(get_kpi_service)],
    anio: Annotated[
        str | None,
        Query(
            description=(
                "Período: 'acumulado' (por defecto) o un año entre 2020 y 2024."
            )
        ),
    ] = None,
) -> KpiResponse:
    """Consulta el documento nacional preagregado y lo expone a la API."""

    try:
        document = service.get(anio)
    except PeriodoInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KpiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except DatabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    return _to_response(document)
