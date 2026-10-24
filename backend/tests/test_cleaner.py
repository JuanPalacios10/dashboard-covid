"""Pruebas unitarias de la normalización y limpieza por chunk."""

from __future__ import annotations

from datetime import date

import pandas as pd
from app.ingestion.cleaner import clean_chunk
from app.ingestion.dedupe import IdDeduplicator
from app.ingestion.schema import FINAL_COLUMNS

from tests.conftest import INTERNAL_COLUMNS, internal_row


def make_raw(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=INTERNAL_COLUMNS)


def test_normaliza_columnas_codigos_edad_y_categorias() -> None:
    raw = make_raw(
        [
            internal_row(
                **{
                    "Código DIVIPOLA departamento": "8.001",
                    "Nombre departamento": "BARRANQUILLA",
                    "Código DIVIPOLA municipio": "8.001",
                    "Nombre municipio": " BARRANQUILLA ",
                    "Edad": "24",
                    "Unidad de medida de edad": "2",
                    "Sexo": "f",
                    "Tipo de contagio": " comunitaria ",
                    "Recuperado": "fallecido",
                }
            )
        ]
    )

    clean, rejected, report = clean_chunk(raw, today=date(2022, 1, 1))

    assert rejected.empty
    assert list(clean.columns) == list(FINAL_COLUMNS)
    row = clean.iloc[0]
    assert row["codigo_divipola_departamento"] == "08"
    assert row["nombre_departamento"] == "ATLÁNTICO"
    assert row["codigo_divipola_municipio"] == "08001"
    assert row["nombre_municipio"] == "BARRANQUILLA"
    assert row["edad"] == 2
    assert row["sexo"] == "F"
    assert row["tipo_contagio"] == "Comunitaria"
    assert row["recuperado"] == "Fallecido"
    assert row["id_caso"] == 1_000_001
    assert row["fecha_reporte_web"].date() == date(2021, 1, 5)
    assert report.corrections["nombre_departamento"] == 1
    assert report.corrections["edad_convertida_desde_meses"] == 1
    assert report.invalid == {}


def test_rechaza_filas_con_datos_criticos_invalidos() -> None:
    raw = make_raw(
        [
            internal_row(
                **{
                    "ID de caso": "no-numerico",
                    "fecha reporte web": "fecha-mala",
                    "Código DIVIPOLA departamento": "XX",
                    "Código DIVIPOLA municipio": "",
                    "Edad": "200",
                }
            )
        ]
    )

    clean, rejected, report = clean_chunk(raw, today=date(2022, 1, 1))

    assert clean.empty
    assert len(rejected) == 1
    motivo = rejected.iloc[0]["motivo_rechazo"]
    assert "id_caso inválido" in motivo
    assert "fecha_reporte_web inválida" in motivo
    assert "código DIVIPOLA departamento inválido" in motivo
    assert "código DIVIPOLA municipio inválido" in motivo
    assert "edad inválida" in motivo
    assert report.rows_rejected == 1
    assert report.rejected_reasons["id_caso inválido"] == 1


def test_deduplica_dentro_y_entre_chunks() -> None:
    deduplicator = IdDeduplicator()

    first = make_raw(
        [
            internal_row(**{"ID de caso": "10"}),
            internal_row(**{"ID de caso": "11"}),
            internal_row(**{"ID de caso": "11"}),
        ]
    )
    clean_first, rejected_first, report_first = clean_chunk(
        first, today=date(2022, 1, 1), deduplicator=deduplicator
    )

    second = make_raw(
        [
            internal_row(**{"ID de caso": "11"}),
            internal_row(**{"ID de caso": "12"}),
        ]
    )
    clean_second, rejected_second, report_second = clean_chunk(
        second, today=date(2022, 1, 1), deduplicator=deduplicator
    )

    assert clean_first["id_caso"].tolist() == [10, 11]
    assert clean_second["id_caso"].tolist() == [12]
    assert report_first.duplicates_removed == 1
    assert report_second.duplicates_removed == 1
    assert len(rejected_first) == 1
    assert len(rejected_second) == 1
    assert rejected_second.iloc[0]["motivo_rechazo"] == "id_caso duplicado"
    assert deduplicator.seen_count == 3


def test_detecta_fechas_futuras_y_conserva_nulos() -> None:
    raw = make_raw(
        [
            internal_row(
                **{
                    "fecha reporte web": "2023-01-01 00:00:00",
                    "Fecha de muerte": "",
                }
            )
        ]
    )

    clean, _rejected, report = clean_chunk(raw, today=date(2022, 1, 1))

    assert len(clean) == 1
    assert report.inconsistencies["fecha_reporte_web_futura"] == 1
    assert report.output_nulls["fecha_muerte"] == 1


def test_convierte_edad_en_dias() -> None:
    raw = make_raw(
        [
            internal_row(
                **{
                    "Edad": "730",
                    "Unidad de medida de edad": "3",
                }
            )
        ]
    )

    clean, _rejected, report = clean_chunk(raw, today=date(2022, 1, 1))

    assert clean.iloc[0]["edad"] == 1
    assert report.corrections["edad_convertida_desde_dias"] == 1
