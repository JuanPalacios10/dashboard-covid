"""Endpoint compuesto del tablero preagregado."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ..database import DatabaseError
from ..services.auth import UserRole
from ..services.dashboard import (
    DashboardNotFoundError,
    DashboardService,
    DepartamentoNotFoundError,
    get_dashboard_service,
)
from ..services.kpis import KpiNotFoundError, PeriodoInvalidoError
from .auth import require_roles
from .kpis import KpiValores

router = APIRouter(prefix="/dashboard", tags=["tablero"])


class DepartamentoRef(BaseModel):
    codigo: str
    nombre: str


class SerieItem(BaseModel):
    codigo: str
    nombre: str
    total: int = Field(ge=0)
    valores: list[int]


class SeriesPayload(BaseModel):
    tipo: str
    anio: int | None
    periodo: str
    granularidad: str
    departamento: DepartamentoRef | None
    fecha_corte: date
    fechas: list[str]
    series: list[SerieItem]


class DepartamentoItem(BaseModel):
    codigo: str
    nombre: str
    total: int = Field(ge=0)
    fallecidos: int = Field(ge=0)
    tasa_letalidad: float = Field(ge=0, le=1)
    participacion: float = Field(ge=0, le=100)


class TerritoriosPayload(BaseModel):
    anio: int | None
    periodo: str
    fecha_corte: date
    total: int = Field(ge=0)
    departamentos: list[DepartamentoItem]


class SexoItem(BaseModel):
    nombre: str
    total: int = Field(ge=0)
    fallecidos: int = Field(ge=0)
    porcentaje: float = Field(ge=0, le=100)
    tasa_letalidad: float = Field(ge=0, le=1)


class EdadItem(BaseModel):
    grupo: str
    total: int = Field(ge=0)
    fallecidos: int = Field(ge=0)
    porcentaje: float = Field(ge=0, le=100)
    tasa_letalidad: float = Field(ge=0, le=1)


class DemografiaPayload(BaseModel):
    anio: int | None
    periodo: str
    fecha_corte: date
    total: int = Field(ge=0)
    sexo: list[SexoItem]
    edad: list[EdadItem]


class HeatmapFila(BaseModel):
    codigo: str
    nombre: str
    total: int = Field(ge=0)
    valores: list[int]


class HeatmapPayload(BaseModel):
    anio: int | None
    periodo: str
    fecha_corte: date
    columnas: list[str]
    filas: list[HeatmapFila]


class DashboardResponse(BaseModel):
    periodo: str
    anio: int | None
    fecha_corte: date
    actualizado_en: datetime
    kpis: KpiValores
    series: SeriesPayload
    territorios: TerritoriosPayload
    demografia: DemografiaPayload
    heatmap: HeatmapPayload


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


def _to_response(payload: dict[str, Any]) -> DashboardResponse:
    try:
        return DashboardResponse(
            periodo=str(payload["periodo"]),
            anio=payload.get("anio"),
            fecha_corte=_coerce_date(payload["fecha_corte"]),
            actualizado_en=_coerce_datetime(payload["actualizado_en"]),
            kpis=KpiValores(**payload["kpis"]),
            series=SeriesPayload(**payload["series"]),
            territorios=TerritoriosPayload(**payload["territorios"]),
            demografia=DemografiaPayload(**payload["demografia"]),
            heatmap=HeatmapPayload(**payload["heatmap"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Los agregados del tablero están incompletos o son inválidos. "
                "Vuelva a ejecutar la consolidación del tablero."
            ),
        ) from exc


@router.get(
    "",
    response_model=DashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Tablero gerencial preagregado",
    description=(
        "Devuelve KPIs, series, territorios, demografía y mapa de calor desde "
        "``dashboard_agregados``. Acepta ``anio=acumulado`` o un año entre "
        "2020 y 2024, y opcionalmente ``departamento``."
    ),
)
def get_dashboard(
    response: Response,
    _current_user: Annotated[
        dict[str, Any],
        Depends(
            require_roles(
                [UserRole.ADMIN, UserRole.ANALISTA, UserRole.EJECUTIVO]
            )
        ),
    ],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    anio: Annotated[
        str,
        Query(
            description=(
                "Período: 'acumulado' o un año entre 2020 y 2024."
            )
        ),
    ] = "acumulado",
    departamento: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=2,
            description="Código DIVIPOLA de departamento, por ejemplo 05.",
        ),
    ] = None,
) -> DashboardResponse:
    """Consulta los documentos preagregados y compone el tablero."""

    try:
        payload = service.get(anio, departamento)
    except PeriodoInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DepartamentoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (DashboardNotFoundError, KpiNotFoundError, DatabaseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    return _to_response(payload)
