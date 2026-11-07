"""Pruebas de las definiciones históricas usadas por el tablero."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.ingestion import dashboard_aggregates


def _base_rows() -> list[dict[str, Any]]:
    return [
        {
            "fecha_reporte_web": date(2021, 1, 1),
            "codigo_divipola_departamento": "05",
            "nombre_departamento": "ANTIOQUIA",
            "codigo_divipola_municipio": "05001",
            "nombre_municipio": "MEDELLIN",
            "edad": 30,
            "sexo": "F",
            "fecha_muerte": date(2021, 1, 10),
            "fecha_recuperacion": None,
        },
        {
            "fecha_reporte_web": date(2021, 1, 2),
            "codigo_divipola_departamento": "05",
            "nombre_departamento": "ANTIOQUIA",
            "codigo_divipola_municipio": "05002",
            "nombre_municipio": "BELLO",
            "edad": 40,
            "sexo": "M",
            "fecha_muerte": None,
            "fecha_recuperacion": date(2021, 6, 1),
        },
        {
            "fecha_reporte_web": date(2021, 12, 20),
            "codigo_divipola_departamento": "05",
            "nombre_departamento": "ANTIOQUIA",
            "codigo_divipola_municipio": "05001",
            "nombre_municipio": "MEDELLIN",
            "edad": 80,
            "sexo": "F",
            "fecha_muerte": None,
            "fecha_recuperacion": None,
        },
        {
            "fecha_reporte_web": date(2021, 12, 31),
            "codigo_divipola_departamento": "11",
            "nombre_departamento": "BOGOTÁ D.C.",
            "codigo_divipola_municipio": "11001",
            "nombre_municipio": "BOGOTA",
            "edad": 10,
            "sexo": "M",
            "fecha_muerte": None,
            "fecha_recuperacion": None,
        },
    ]


def _write_parquet(
    tmp_path: Path,
    year: int = 2021,
    rows: list[dict[str, Any]] | None = None,
) -> Path:
    frame = pd.DataFrame(rows if rows is not None else _base_rows())
    directory = tmp_path / f"anio={year}"
    directory.mkdir(parents=True)
    path = directory / "casos.parquet"
    pq.write_table(pa.Table.from_pandas(frame), path)
    return tmp_path


def _capture_documents(monkeypatch) -> dict[str, list[dict[str, Any]]]:
    captured: dict[str, list[dict[str, Any]]] = {
        "kpis": [],
        "dashboard": [],
    }

    def fake_replace(collection: Any, documents: list[dict[str, Any]]) -> None:
        key = "kpis" if collection == "kpis" else "dashboard"
        captured[key].extend(documents)

    monkeypatch.setattr(
        dashboard_aggregates, "_replace_documents", fake_replace
    )
    return captured


def test_consolidacion_usa_fechas_terminales_y_cohorte_anual(
    tmp_path: Path, monkeypatch
) -> None:
    parquet_dir = _write_parquet(tmp_path)
    captured = _capture_documents(monkeypatch)

    summary = dashboard_aggregates.consolidate_dashboard_from_parquet(
        parquet_dir,
        "dashboard",
        "kpis",
    )

    assert summary["confirmados"] == 4
    assert summary["fallecidos"] == 1
    assert summary["recuperados"] == 1
    assert summary["activos"] == 2

    kpis = {document["_id"]: document for document in captured["kpis"]}
    assert kpis["2021"]["casos_confirmados"] == 4
    assert kpis["2021"]["fallecidos"] == 1
    assert kpis["2021"]["recuperados"] == 1
    assert kpis["2021"]["activos"] == 2
    assert kpis["nacional"]["activos"] == 2

    dashboard = {
        document["_id"]: document for document in captured["dashboard"]
    }
    series = dashboard["series:departamento:05:2021"]
    assert series["departamento"]["nombre"] == "ANTIOQUIA"
    assert series["series"][0]["nombre"] == "MEDELLIN"
    assert sum(series["series"][0]["valores"]) == 2
    assert dashboard["territorios:2021"]["departamentos"][0]["codigo"] == "05"
    assert dashboard["demografia:2021"]["total"] == 4
    assert dashboard["heatmap:2021"]["columnas"][0] == "Ene"


def test_consolidacion_completa_series_cero_para_departamentos_sin_casos(
    tmp_path: Path, monkeypatch
) -> None:
    _write_parquet(tmp_path)
    _write_parquet(
        tmp_path,
        year=2022,
        rows=[
            {
                "fecha_reporte_web": date(2022, 1, 5),
                "codigo_divipola_departamento": "11",
                "nombre_departamento": "BOGOTÁ D.C.",
                "codigo_divipola_municipio": "11001",
                "nombre_municipio": "BOGOTA",
                "edad": 20,
                "sexo": "F",
                "fecha_muerte": None,
                "fecha_recuperacion": None,
            }
        ],
    )
    captured = _capture_documents(monkeypatch)

    dashboard_aggregates.consolidate_dashboard_from_parquet(
        tmp_path,
        "dashboard",
        "kpis",
    )

    dashboard = {
        document["_id"]: document for document in captured["dashboard"]
    }
    zero_series = dashboard["series:departamento:05:2022"]
    assert zero_series["departamento"]["nombre"] == "ANTIOQUIA"
    assert zero_series["series"][0]["nombre"] == "Sin casos"
    assert zero_series["series"][0]["total"] == 0
