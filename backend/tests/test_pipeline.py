"""Pruebas de integración del pipeline de ingesta."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from app.ingestion.memory import MemoryLimitExceeded
from app.ingestion.pipeline import (
    DatasetSchemaError,
    IngestionConfig,
    OutputAlreadyExists,
    run_ingestion,
)
from app.ingestion.schema import FINAL_COLUMNS

from tests.conftest import SOURCE_HEADERS, source_row


def config_for(source: Path, output: Path, **overrides: object) -> IngestionConfig:
    values = {
        "source_path": source,
        "output_dir": output,
        "chunk_size": 2,
        "memory_limit_mb": 4_096,
        "overwrite": True,
    }
    values.update(overrides)
    return IngestionConfig(**values)  # type: ignore[arg-type]


def test_ingesta_completa_particiona_deduplica_y_rechaza(
    sample_csv: Path, tmp_path: Path
) -> None:
    output = tmp_path / "processed"
    manifest = run_ingestion(config_for(sample_csv, output))

    # 3 filas válidas (el duplicado y la fila inválida se rechazan).
    assert manifest["estado"] == "completado"
    assert manifest["totales"]["rows_read"] == 5
    assert manifest["totales"]["rows_clean"] == 3
    assert manifest["totales"]["rows_rejected"] == 2
    assert manifest["totales"]["duplicates_removed"] == 1
    assert manifest["chunks_procesados"] == 3  # 5 filas / chunk_size 2

    cases_dir = output / "casos"
    assert (cases_dir / "anio=2020" / "casos.parquet").is_file()
    assert (cases_dir / "anio=2021" / "casos.parquet").is_file()

    cases = pd.read_parquet(cases_dir)
    assert len(cases) == 3
    assert [column for column in cases.columns if column != "anio"] == list(
        FINAL_COLUMNS
    )
    assert cases["id_caso"].is_unique
    assert set(cases["anio"]) == {2020, 2021}

    rejected = pd.read_parquet(output / "rechazados")
    assert len(rejected) == 2
    assert set(rejected["motivo_rechazo"]) == {
        "id_caso duplicado",
        (
            "fecha_reporte_web inválida; código DIVIPOLA departamento inválido; "
            "código DIVIPOLA municipio inválido; edad inválida"
        ),
    }

    manifest_path = Path(manifest["manifiesto"])
    assert manifest_path.is_file()
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["totales"]["rows_clean"] == 3
    assert loaded["memoria"]["dentro_del_limite"] is True

    # La partición virtual, agregada al leer el dataset, no se guarda como
    # columna física dentro del archivo.
    assert "anio" not in pd.read_parquet(
        cases_dir / "anio=2021" / "casos.parquet"
    ).columns


def test_no_sobrescribe_por_defecto(sample_csv: Path, tmp_path: Path) -> None:
    output = tmp_path / "processed"
    run_ingestion(config_for(sample_csv, output))

    with pytest.raises(OutputAlreadyExists):
        run_ingestion(config_for(sample_csv, output, overwrite=False))

    # Con overwrite vuelve a publicar sin dejar staging.
    manifest = run_ingestion(config_for(sample_csv, output, overwrite=True))
    assert manifest["estado"] == "completado"
    assert not list(output.glob(".staging-*"))


def test_limit_rows_detiene_la_lectura(sample_csv: Path, tmp_path: Path) -> None:
    output = tmp_path / "processed"
    manifest = run_ingestion(
        config_for(sample_csv, output, limit_rows=2, chunk_size=10)
    )
    assert manifest["totales"]["rows_read"] == 2
    assert manifest["totales"]["rows_clean"] == 2
    assert manifest["chunks_procesados"] == 1


def test_falla_si_falta_una_columna(tmp_path: Path) -> None:
    source = tmp_path / "incompleto.csv"
    row = source_row()
    row.pop("Sexo")
    pd.DataFrame([row]).to_csv(source, index=False)

    output = tmp_path / "processed"
    with pytest.raises(DatasetSchemaError, match="Sexo"):
        run_ingestion(config_for(source, output))


def test_aborta_y_no_publica_si_supera_el_limite_de_memoria(
    sample_csv: Path, tmp_path: Path
) -> None:
    output = tmp_path / "processed"

    with pytest.raises(MemoryLimitExceeded):
        run_ingestion(config_for(sample_csv, output, memory_limit_mb=16))

    assert not (output / "casos").exists()
    manifests = list((output / "manifests").glob("ingesta_*.json"))
    assert len(manifests) == 1
    failed = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert failed["estado"] == "fallido"
    assert "MemoryLimitExceeded" in failed["error"]
    assert not list(output.glob(".staging-*"))


def test_sin_dedupe_conserva_duplicados(sample_csv: Path, tmp_path: Path) -> None:
    output = tmp_path / "processed"
    manifest = run_ingestion(
        config_for(sample_csv, output, deduplicate=False)
    )
    # 4 filas válidas: el id 1.000.001 aparece dos veces.
    assert manifest["totales"]["rows_clean"] == 4
    assert manifest["totales"]["duplicates_removed"] == 0
    assert manifest["totales"]["rows_rejected"] == 1


def test_columnas_de_origen_extra_son_ignoradas(tmp_path: Path) -> None:
    # El fixture ya incluye columnas no esenciales (Estado, país, etc.).
    assert "Estado" in SOURCE_HEADERS
    assert "Estado" not in list(FINAL_COLUMNS)


def test_ingesta_json_lines(tmp_path: Path) -> None:
    source = tmp_path / "casos.jsonl"
    rows = [
        source_row(**{"ID de caso": "1.000.010"}),
        source_row(
            **{
                "ID de caso": "1.000.011",
                "fecha reporte web": "2020-07-01 00:00:00",
                "Fecha de notificación": "2020-06-29 00:00:00",
                "Edad": "15",
                "Unidad de medida de edad": "1",
            }
        ),
    ]
    pd.DataFrame(rows, columns=SOURCE_HEADERS).to_json(
        source, orient="records", lines=True, force_ascii=False
    )

    output = tmp_path / "processed"
    manifest = run_ingestion(config_for(source, output))

    assert manifest["totales"]["rows_read"] == 2
    assert manifest["totales"]["rows_clean"] == 2
    cases = pd.read_parquet(output / "casos")
    assert len(cases) == 2
    assert set(cases["anio"]) == {2020, 2021}
    assert cases["codigo_divipola_departamento"].unique().tolist() == ["76"]
