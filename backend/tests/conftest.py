"""Fixtures y utilidades para las pruebas."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

SOURCE_HEADERS = [
    "fecha reporte web",
    "ID de caso",
    "Fecha de notificación",
    "Código DIVIPOLA departamento",
    "Nombre departamento",
    "Código DIVIPOLA municipio",
    "Nombre municipio",
    "Edad",
    "Unidad de medida de edad",
    "Sexo",
    "Tipo de contagio",
    "Ubicación del caso",
    "Estado",
    "Código ISO del país",
    "Nombre del país",
    "Recuperado",
    "Fecha de inicio de síntomas",
    "Fecha de muerte",
    "Fecha de diagnóstico",
    "Fecha de recuperación",
    "Tipo de recuperación",
    "Pertenencia étnica",
    "Nombre del grupo étnico",
]

INTERNAL_COLUMNS = [
    "fecha_reporte_web",
    "id_caso",
    "fecha_notificacion",
    "codigo_divipola_departamento",
    "nombre_departamento",
    "codigo_divipola_municipio",
    "nombre_municipio",
    "edad",
    "_unidad_edad",
    "sexo",
    "tipo_contagio",
    "recuperado",
    "fecha_inicio_sintomas",
    "fecha_muerte",
    "fecha_diagnostico",
    "fecha_recuperacion",
]


def source_row(**overrides: object) -> dict[str, object]:
    """Fila completa con valores válidos, modificable por columna original."""

    row: dict[str, object] = {
        "fecha reporte web": "2021-01-05 00:00:00",
        "ID de caso": "1.000.001",
        "Fecha de notificación": "2021-01-03 00:00:00",
        "Código DIVIPOLA departamento": "76",
        "Nombre departamento": "VALLE",
        "Código DIVIPOLA municipio": "76.001",
        "Nombre municipio": "CALI",
        "Edad": "34",
        "Unidad de medida de edad": "1",
        "Sexo": "F",
        "Tipo de contagio": "Comunitaria",
        "Ubicación del caso": "Casa",
        "Estado": "Leve",
        "Código ISO del país": "",
        "Nombre del país": "",
        "Recuperado": "Recuperado",
        "Fecha de inicio de síntomas": "2021-01-01 00:00:00",
        "Fecha de muerte": "",
        "Fecha de diagnóstico": "2021-01-02 00:00:00",
        "Fecha de recuperación": "2021-01-10 00:00:00",
        "Tipo de recuperación": "Tiempo",
        "Pertenencia étnica": "6",
        "Nombre del grupo étnico": "",
    }
    row.update(overrides)
    return row


def internal_row(**overrides: object) -> dict[str, object]:
    """Fila con nombres internos (salida esperada del renombrado)."""

    source = source_row(**overrides)
    rename = {
        "fecha reporte web": "fecha_reporte_web",
        "ID de caso": "id_caso",
        "Fecha de notificación": "fecha_notificacion",
        "Código DIVIPOLA departamento": "codigo_divipola_departamento",
        "Nombre departamento": "nombre_departamento",
        "Código DIVIPOLA municipio": "codigo_divipola_municipio",
        "Nombre municipio": "nombre_municipio",
        "Edad": "edad",
        "Unidad de medida de edad": "_unidad_edad",
        "Sexo": "sexo",
        "Tipo de contagio": "tipo_contagio",
        "Recuperado": "recuperado",
        "Fecha de inicio de síntomas": "fecha_inicio_sintomas",
        "Fecha de muerte": "fecha_muerte",
        "Fecha de diagnóstico": "fecha_diagnostico",
        "Fecha de recuperación": "fecha_recuperacion",
    }
    return {rename[key]: value for key, value in source.items() if key in rename}


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    """CSV pequeño con dos años, duplicado y una fila inválida."""

    rows = [
        source_row(**{"ID de caso": "1.000.001"}),
        source_row(
            **{
                "ID de caso": "1.000.002",
                "fecha reporte web": "2020-06-01 00:00:00",
                "Fecha de notificación": "2020-05-30 00:00:00",
                "Edad": "24",
                "Unidad de medida de edad": "2",
            }
        ),
        source_row(
            **{
                "ID de caso": "1.000.003",
                "Código DIVIPOLA departamento": "8.001",
                "Nombre departamento": "BARRANQUILLA",
                "Código DIVIPOLA municipio": "8.001",
                "Nombre municipio": "BARRANQUILLA",
                "Sexo": "m",
                "fecha reporte web": "2021-02-01 00:00:00",
                "Fecha de notificación": "2021-01-30 00:00:00",
            }
        ),
        # Duplicado del primer id, en otro chunk.
        source_row(**{"ID de caso": "1.000.001"}),
        # Inválida: fecha de reporte imposible, edad fuera de rango y código malo.
        source_row(
            **{
                "ID de caso": "1.000.005",
                "fecha reporte web": "no-es-fecha",
                "Código DIVIPOLA departamento": "XX",
                "Código DIVIPOLA municipio": "",
                "Edad": "200",
            }
        ),
    ]
    path = tmp_path / "casos.csv"
    pd.DataFrame(rows, columns=SOURCE_HEADERS).to_csv(path, index=False)
    return path
