"""Servicio de proyecciones construido sobre las bases precalculadas."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from .dashboard import (
    DashboardRepository,
    DashboardRepositoryProtocol,
    DepartamentoNotFoundError,
)
from .kpis import KpiService, get_kpi_service

HORIZONTES_VALIDOS = frozenset({30, 60, 90})
GENERATION_DAYS = 5.0
RECOVERY_DAYS = 10.0
Z_80 = 1.2815515655


class ProyeccionNotFoundError(Exception):
    """No existe la base precalculada para el período o territorio."""


class ProyeccionValidationError(ValueError):
    """Parámetros de proyección inválidos."""


def _normalize_departamento(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.isdigit():
        return normalized.zfill(2)
    return normalized


def _moving_average(values: list[int], window: int = 7) -> list[float]:
    result: list[float] = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        chunk = values[start : index + 1]
        result.append(round(sum(chunk) / len(chunk), 2))
    return result


def _quality_factor(level: str) -> float:
    return {
        "alta": 1.0,
        "media": 1.3,
        "baja": 1.6,
    }.get(level, 1.3)


def _date_at(cutoff: date, days: int) -> str:
    return (cutoff + timedelta(days=days)).isoformat()


def _project_scenario(
    *,
    scenario_id: str,
    name: str,
    r_base: float,
    medidas: float,
    base: dict[str, Any],
    quality_factor: float,
    horizonte: int,
    cutoff: date,
) -> dict[str, Any]:
    r_effect = r_base * (1 - 0.5 * medidas / 100)
    average = float(base.get("promedio_7d_actual", 0) or 0)
    active = float(base.get("activos_al_corte", 0) or 0)
    capacity = max(
        float(base.get("max_7d_periodo", 0) or 0) * 2.0,
        average * 2.0,
        1.0,
    )

    full_new: list[float] = []
    full_active: list[float] = []
    lower_new: list[float] = []
    upper_new: list[float] = []
    lower_active: list[float] = []
    upper_active: list[float] = []

    for day in range(1, 91):
        growth = (r_effect - 1) / GENERATION_DAYS
        saturation = max(0.0, 1.0 - average / capacity)
        average = max(0.0, average * math.exp(growth * saturation))
        recovered = active / RECOVERY_DAYS
        active = max(0.0, active + average - recovered)

        new_sigma = math.sqrt(max(average, 0.0))
        active_sigma = math.sqrt(max(active, 0.0))
        margin_new = Z_80 * quality_factor * new_sigma
        margin_active = Z_80 * quality_factor * active_sigma

        full_new.append(round(average, 2))
        full_active.append(round(active, 2))
        lower_new.append(round(max(0.0, average - margin_new), 2))
        upper_new.append(round(average + margin_new, 2))
        lower_active.append(round(max(0.0, active - margin_active), 2))
        upper_active.append(round(active + margin_active, 2))

    peak_index = max(
        range(horizonte), key=lambda index: full_active[index]
    )
    peak_new_index = max(
        range(horizonte), key=lambda index: full_new[index]
    )
    return {
        "id": scenario_id,
        "nombre": name,
        "r_base": round(r_base, 2),
        "medidas": medidas,
        "r_efectivo": round(r_effect, 3),
        "nuevos": full_new[:horizonte],
        "activos": full_active[:horizonte],
        "banda_nuevos": {
            "inferior": lower_new[:horizonte],
            "superior": upper_new[:horizonte],
        },
        "banda_activos": {
            "inferior": lower_active[:horizonte],
            "superior": upper_active[:horizonte],
        },
        "resumen": {
            "nuevos_30d": round(sum(full_new[:30])),
            "nuevos_60d": round(sum(full_new[:60])),
            "nuevos_90d": round(sum(full_new[:90])),
            "pico_activos": round(max(full_active[:horizonte])),
            "fecha_pico": _date_at(cutoff, peak_index + 1),
            "pico_nuevos": round(max(full_new[:horizonte])),
            "fecha_pico_nuevos": _date_at(cutoff, peak_new_index + 1),
        },
    }


class ProyeccionService:
    """Compone la respuesta de proyecciones a partir de la base precalculada."""

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
        horizonte: int = 60,
        r: float | None = None,
        medidas: float = 40.0,
    ) -> dict[str, Any]:
        normalized_periodo = self.kpi_service.normalize_periodo(periodo)
        normalized_departamento = _normalize_departamento(departamento)

        if horizonte not in HORIZONTES_VALIDOS:
            raise ProyeccionValidationError(
                "El horizonte debe ser 30, 60 o 90 días."
            )
        if r is not None and not 0.3 <= r <= 3.0:
            raise ProyeccionValidationError(
                "El R base debe estar entre 0.3 y 3.0."
            )
        if not 0 <= medidas <= 100:
            raise ProyeccionValidationError(
                "Las medidas deben estar entre 0 y 100."
            )

        if normalized_departamento:
            doc_id = (
                f"proyeccion:departamento:"
                f"{normalized_departamento}:{normalized_periodo}"
            )
        else:
            doc_id = f"proyeccion:nacional:{normalized_periodo}"

        document = self.repository.get(doc_id)
        if document is None:
            if normalized_departamento:
                territories = self.repository.get(
                    f"territorios:{normalized_periodo}"
                )
                if territories is not None:
                    known = {
                        str(item.get("codigo"))
                        for item in territories.get("departamentos", [])
                    }
                    if normalized_departamento not in known:
                        raise DepartamentoNotFoundError(
                            "El departamento solicitado no existe en el dataset."
                        )
            raise ProyeccionNotFoundError(
                "No hay base de proyección para el período "
                f"'{normalized_periodo}'. Ejecute la consolidación del tablero."
            )

        base = dict(document.get("base", {}))
        base_values = [
            int(value) for value in base.get("casos_diarios", [])
        ]
        if not base_values:
            raise ProyeccionNotFoundError(
                "La base de proyección está incompleta."
            )

        cutoff_value = document.get("fecha_corte")
        if isinstance(cutoff_value, datetime):
            cutoff = cutoff_value.date()
        elif isinstance(cutoff_value, date):
            cutoff = cutoff_value
        elif isinstance(cutoff_value, str):
            cutoff = date.fromisoformat(cutoff_value[:10])
        else:
            raise ProyeccionNotFoundError(
                "La fecha de corte de la proyección no es válida."
            )

        calidad = dict(document.get("calidad", {}))
        quality_factor = _quality_factor(str(calidad.get("nivel", "media")))
        r_estimado = max(0.0, min(3.0, float(base.get("r_estimado", 0) or 0)))
        r_custom = float(r) if r is not None else max(0.3, r_estimado)
        r_custom = max(0.3, min(3.0, r_custom))

        presets = [
            ("optimista", "Optimista", 1.0, 80.0),
            ("moderado", "Moderado", 1.3, 40.0),
            ("pesimista", "Pesimista", 1.6, 10.0),
        ]
        scenarios = [
            _project_scenario(
                scenario_id=scenario_id,
                name=name,
                r_base=r_base,
                medidas=scenario_measures,
                base=base,
                quality_factor=quality_factor,
                horizonte=horizonte,
                cutoff=cutoff,
            )
            for scenario_id, name, r_base, scenario_measures in presets
        ]
        scenarios.append(
            _project_scenario(
                scenario_id="personalizado",
                name="Tu simulación",
                r_base=r_custom,
                medidas=medidas,
                base=base,
                quality_factor=quality_factor,
                horizonte=horizonte,
                cutoff=cutoff,
            )
        )

        moderate = next(
            scenario for scenario in scenarios if scenario["id"] == "moderado"
        )
        observed = document.get("observado_posterior")
        backtest = None
        if observed and observed.get("fechas"):
            observed_values = [
                int(value) for value in observed.get("casos_diarios", [])
            ]
            days = min(
                horizonte,
                len(observed["fechas"]),
                len(observed_values),
            )
            if days > 0:
                projected = moderate["nuevos"][:days]
                actual = observed_values[:days]
                absolute_errors = [
                    abs(projected_value - actual_value)
                    for projected_value, actual_value in zip(
                        projected, actual
                    )
                ]
                mae = sum(absolute_errors) / days
                relative = [
                    (2 * abs(projected_value - actual_value))
                    / (abs(projected_value) + abs(actual_value))
                    * 100
                    for projected_value, actual_value in zip(
                        projected, actual
                    )
                    if abs(projected_value) + abs(actual_value) > 0
                ]
                backtest = {
                    "fechas": observed["fechas"][:days],
                    "observado": actual,
                    "proyectado": projected,
                    "mae": round(mae, 2),
                    "smape": round(sum(relative) / len(relative), 2)
                    if relative
                    else None,
                    "dias_comparados": days,
                }

        return {
            "periodo": str(document.get("periodo", "anual")),
            "anio": document.get("anio"),
            "departamento": document.get("departamento"),
            "fecha_corte": cutoff.isoformat(),
            "horizonte": horizonte,
            "r_estimado": r_estimado,
            "calidad": calidad,
            "base": {
                "fechas": base.get("fechas", []),
                "casos_diarios": base_values,
                "promedio_7d": _moving_average(base_values),
                "activos_diarios": base.get("activos_diarios", []),
                "activos_al_corte": int(
                    base.get("activos_al_corte", 0) or 0
                ),
                "promedio_7d_actual": float(
                    base.get("promedio_7d_actual", 0) or 0
                ),
                "r_estimado": r_estimado,
            },
            "observado_posterior": observed,
            "fechas_proyeccion": [
                _date_at(cutoff, day) for day in range(1, horizonte + 1)
            ],
            "escenarios": scenarios,
            "backtest": backtest,
        }


def get_proyeccion_service() -> ProyeccionService:
    """Proveedor de dependencia para FastAPI."""

    return ProyeccionService()
