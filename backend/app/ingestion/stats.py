"""Acumulación de métricas de calidad durante la ingesta por chunks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .schema import FINAL_COLUMNS


@dataclass
class ChunkReport:
    """Métricas calculadas para un único bloque (chunk) del dataset."""

    rows_read: int = 0
    rows_clean: int = 0  # filas válidas antes de deduplicar
    rows_rejected: int = 0
    duplicates_removed: int = 0

    raw_nulls: Counter[str] = field(default_factory=Counter)
    output_nulls: Counter[str] = field(default_factory=Counter)

    invalid: Counter[str] = field(default_factory=Counter)
    corrections: Counter[str] = field(default_factory=Counter)
    inconsistencies: Counter[str] = field(default_factory=Counter)
    rejected_reasons: Counter[str] = field(default_factory=Counter)

    date_min: dict[str, date] = field(default_factory=dict)
    date_max: dict[str, date] = field(default_factory=dict)

    age_min: int | None = None
    age_max: int | None = None
    age_sum: int = 0
    age_count: int = 0

    categories: dict[str, Counter[str]] = field(
        default_factory=lambda: {
            "sexo": Counter(),
            "tipo_contagio": Counter(),
            "recuperado": Counter(),
            "unidad_edad": Counter(),
        }
    )

    departments: Counter[str] = field(default_factory=Counter)
    municipalities: Counter[str] = field(default_factory=Counter)


def count_values(series: Any) -> Counter[str]:
    """Cuenta valores incluyendo nulos, representados como ``"<NA>"``."""

    counts = series.fillna("<NA>").astype("string").value_counts()
    return Counter({str(key): int(value) for key, value in counts.items()})


def summarize_reports(reports: list[ChunkReport]) -> dict[str, Any]:
    """Consolida los reportes de todos los chunks en un resumen serializable."""

    totals = {
        "rows_read": sum(report.rows_read for report in reports),
        "rows_clean": sum(report.rows_clean for report in reports),
        "rows_rejected": sum(report.rows_rejected for report in reports),
        "duplicates_removed": sum(report.duplicates_removed for report in reports),
    }

    raw_nulls: Counter[str] = Counter()
    output_nulls: Counter[str] = Counter()
    invalid: Counter[str] = Counter()
    corrections: Counter[str] = Counter()
    inconsistencies: Counter[str] = Counter()
    rejected_reasons: Counter[str] = Counter()
    departments: Counter[str] = Counter()
    municipalities: Counter[str] = Counter()

    date_min: dict[str, date] = {}
    date_max: dict[str, date] = {}
    age_min: int | None = None
    age_max: int | None = None
    age_sum = 0
    age_count = 0

    categories: dict[str, Counter[str]] = {
        "sexo": Counter(),
        "tipo_contagio": Counter(),
        "recuperado": Counter(),
        "unidad_edad": Counter(),
    }

    for report in reports:
        raw_nulls.update(report.raw_nulls)
        output_nulls.update(report.output_nulls)
        invalid.update(report.invalid)
        corrections.update(report.corrections)
        inconsistencies.update(report.inconsistencies)
        rejected_reasons.update(report.rejected_reasons)
        departments.update(report.departments)
        municipalities.update(report.municipalities)

        for name, value in report.date_min.items():
            if value is not None:
                date_min[name] = min(value, date_min.get(name, value))
        for name, value in report.date_max.items():
            if value is not None:
                date_max[name] = max(value, date_max.get(name, value))

        if report.age_min is not None:
            age_min = report.age_min if age_min is None else min(age_min, report.age_min)
        if report.age_max is not None:
            age_max = report.age_max if age_max is None else max(age_max, report.age_max)
        age_sum += report.age_sum
        age_count += report.age_count

        for name, counter in report.categories.items():
            categories.setdefault(name, Counter()).update(counter)

    rows_clean = totals["rows_clean"]
    columns_summary = []
    for name in FINAL_COLUMNS:
        nulls = int(output_nulls.get(name, 0))
        columns_summary.append(
            {
                "nombre": name,
                "nulos": nulls,
                "porcentaje_nulos": round(nulls / rows_clean * 100, 4) if rows_clean else 0.0,
            }
        )

    return {
        "totales": {
            **totals,
            "tasa_rechazo_porcentaje": (
                round(totals["rows_rejected"] / totals["rows_read"] * 100, 4)
                if totals["rows_read"]
                else 0.0
            ),
        },
        "columnas": columns_summary,
        "nulos_entrada": dict(sorted(raw_nulls.items())),
        "rangos_fecha": {
            name: {
                "min": date_min.get(name).isoformat() if date_min.get(name) else None,
                "max": date_max.get(name).isoformat() if date_max.get(name) else None,
            }
            for name in sorted(set(date_min) | set(date_max))
        },
        "edad": {
            "min": age_min,
            "max": age_max,
            "promedio": round(age_sum / age_count, 2) if age_count else None,
        },
        "categorias": {name: dict(sorted(counter.items())) for name, counter in categories.items()},
        "departamentos": [
            {"codigo": code, "nombre": name, "casos": departments.get(name, 0)}
            for code, name in sorted(_departments_by_code(departments).items())
        ],
        "calidad": {
            "valores_invalidos": dict(sorted(invalid.items())),
            "correcciones": dict(sorted(corrections.items())),
            "inconsistencias": dict(sorted(inconsistencies.items())),
            "motivos_rechazo": dict(sorted(rejected_reasons.items())),
        },
        "municipios_distintos": len(municipalities),
    }


def _departments_by_code(departments: Counter[str]) -> dict[str, str]:
    from .schema import DEPARTAMENTOS_DANE

    name_to_code = {name: code for code, name in DEPARTAMENTOS_DANE.items()}
    result: dict[str, str] = {}
    for name in departments:
        result[name_to_code.get(name, "")] = name
    return result
