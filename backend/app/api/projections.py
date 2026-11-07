"""Endpoint de proyecciones por año y territorio."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ..database import DatabaseError
from ..services.auth import UserRole
from ..services.dashboard import DepartamentoNotFoundError
from ..services.kpis import KpiNotFoundError, PeriodoInvalidoError
from ..services.projections import (
    ProyeccionNotFoundError,
    ProyeccionService,
    ProyeccionValidationError,
    get_proyeccion_service,
)
from .auth import require_roles

router = APIRouter(prefix="/proyecciones", tags=["proyecciones"])


class DepartamentoRef(BaseModel):
    codigo: str
    nombre: str


class CalidadProyeccion(BaseModel):
    nivel: str
    dias_base: int = Field(ge=0)
    dias_con_datos: int = Field(ge=0)
    mensaje: str


class BaseProyeccion(BaseModel):
    fechas: list[str]
    casos_diarios: list[int]
    promedio_7d: list[float]
    activos_diarios: list[int]
    activos_al_corte: int = Field(ge=0)
    promedio_7d_actual: float = Field(ge=0)
    r_estimado: float = Field(ge=0)


class ObservadoPosterior(BaseModel):
    fechas: list[str]
    casos_diarios: list[int]


class Banda(BaseModel):
    inferior: list[float]
    superior: list[float]


class ResumenEscenario(BaseModel):
    nuevos_30d: int = Field(ge=0)
    nuevos_60d: int = Field(ge=0)
    nuevos_90d: int = Field(ge=0)
    pico_activos: int = Field(ge=0)
    fecha_pico: date
    pico_nuevos: int = Field(ge=0)
    fecha_pico_nuevos: date


class EscenarioProyeccion(BaseModel):
    id: str
    nombre: str
    r_base: float = Field(ge=0)
    medidas: float = Field(ge=0, le=100)
    r_efectivo: float = Field(ge=0)
    nuevos: list[float]
    activos: list[float]
    banda_nuevos: Banda
    banda_activos: Banda
    resumen: ResumenEscenario


class BacktestProyeccion(BaseModel):
    fechas: list[str]
    observado: list[int]
    proyectado: list[float]
    mae: float = Field(ge=0)
    smape: float | None = Field(default=None, ge=0)
    dias_comparados: int = Field(ge=0)


class ProyeccionResponse(BaseModel):
    periodo: str
    anio: int | None
    departamento: DepartamentoRef | None
    fecha_corte: date
    horizonte: int
    r_estimado: float = Field(ge=0)
    calidad: CalidadProyeccion
    base: BaseProyeccion
    observado_posterior: ObservadoPosterior | None
    fechas_proyeccion: list[str]
    escenarios: list[EscenarioProyeccion]
    backtest: BacktestProyeccion | None


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"Fecha no válida: {value!r}")


def _to_response(payload: dict[str, Any]) -> ProyeccionResponse:
    try:
        return ProyeccionResponse(
            periodo=str(payload["periodo"]),
            anio=payload.get("anio"),
            departamento=payload.get("departamento"),
            fecha_corte=_coerce_date(payload["fecha_corte"]),
            horizonte=int(payload["horizonte"]),
            r_estimado=float(payload["r_estimado"]),
            calidad=CalidadProyeccion(**payload["calidad"]),
            base=BaseProyeccion(**payload["base"]),
            observado_posterior=(
                ObservadoPosterior(**payload["observado_posterior"])
                if payload.get("observado_posterior")
                else None
            ),
            fechas_proyeccion=payload["fechas_proyeccion"],
            escenarios=[
                EscenarioProyeccion(**scenario)
                for scenario in payload["escenarios"]
            ],
            backtest=(
                BacktestProyeccion(**payload["backtest"])
                if payload.get("backtest")
                else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "La base de proyección está incompleta o es inválida. "
                "Vuelva a ejecutar la consolidación del tablero."
            ),
        ) from exc


@router.get(
    "",
    response_model=ProyeccionResponse,
    status_code=status.HTTP_200_OK,
    summary="Proyecciones por año y territorio",
    description=(
        "Proyecta casos nuevos y activos usando la base histórica "
        "precalculada. Acepta ``anio=acumulado`` o ``2020``–``2024``, "
        "``departamento``, ``horizonte`` 30/60/90, ``r`` y ``medidas``."
    ),
)
def get_proyecciones(
    response: Response,
    _current_user: Annotated[
        dict[str, Any],
        Depends(
            require_roles(
                [UserRole.ADMIN, UserRole.ANALISTA, UserRole.EJECUTIVO]
            )
        ),
    ],
    service: Annotated[ProyeccionService, Depends(get_proyeccion_service)],
    anio: Annotated[
        str,
        Query(description="Período: 'acumulado' o un año entre 2020 y 2024."),
    ] = "acumulado",
    departamento: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=2,
            description="Código DIVIPOLA de departamento, por ejemplo 05.",
        ),
    ] = None,
    horizonte: Annotated[
        int,
        Query(description="Horizonte de proyección: 30, 60 o 90 días."),
    ] = 60,
    r: Annotated[
        float | None,
        Query(description="R base de la simulación personalizada."),
    ] = None,
    medidas: Annotated[
        float,
        Query(description="Rigor de las medidas sanitarias (0-100)."),
    ] = 40,
) -> ProyeccionResponse:
    """Consulta la base precalculada y ejecuta el modelo de proyección."""

    try:
        payload = service.get(
            periodo=anio,
            departamento=departamento,
            horizonte=horizonte,
            r=r,
            medidas=medidas,
        )
    except (PeriodoInvalidoError, ProyeccionValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DepartamentoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (ProyeccionNotFoundError, KpiNotFoundError, DatabaseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    return _to_response(payload)
