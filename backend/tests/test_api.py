"""Pruebas básicas de la API."""

from __future__ import annotations

import time
from pathlib import Path

from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_estado_sin_ingesta() -> None:
    response = client.get("/api/v1/ingesta/estado")
    assert response.status_code == 200
    body = response.json()
    assert "job" in body
    assert body["job"]["estado"] in {"inactivo", "completado", "fallido", "en_ejecucion"}


def test_valida_chunk_size() -> None:
    response = client.post("/api/v1/ingesta", json={"chunk_size": 10})
    assert response.status_code == 422


def test_valida_memory_limit() -> None:
    response = client.post("/api/v1/ingesta", json={"memory_limit_mb": 10})
    assert response.status_code == 422


def test_ingesta_en_segundo_plano(
    sample_csv: Path, tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "processed"
    monkeypatch.setenv("COVID_DATASET_PATH", str(sample_csv))
    monkeypatch.setenv("COVID_PROCESSED_DIR", str(output))
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/ingesta",
            json={"chunk_size": 1000, "overwrite": True},
        )
        assert response.status_code == 202
        assert response.json()["job"]["estado"] == "en_ejecucion"

        deadline = time.time() + 10
        state = {}
        while time.time() < deadline:
            state = client.get("/api/v1/ingesta/estado").json()["job"]
            if state["estado"] in {"completado", "fallido"}:
                break
            time.sleep(0.05)

        assert state["estado"] == "completado", state
        assert state["progreso"]["filas_leidas"] == 5
        assert (output / "casos").is_dir()
        assert state["manifiesto"] is not None
    finally:
        get_settings.cache_clear()
