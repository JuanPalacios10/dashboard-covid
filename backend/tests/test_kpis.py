"""Pruebas del endpoint de KPIs gerenciales y su contrato de respuesta."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.ingestion.mongo_writer import _to_document
from app.main import app
from app.services.kpis import KpiService, get_kpi_service

client = TestClient(app)


class FakeKpiRepository:
    """Repositorio en memoria para aislar la prueba de MongoDB."""

    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def get(self, doc_id: str) -> dict[str, Any] | None:
        return self.documents.get(doc_id)


def _document(doc_id: str = "nacional") -> dict[str, Any]:
    anual = doc_id != "nacional"
    return {
        "_id": doc_id,
        "scope": "nacional",
        "periodo": "anual" if anual else "acumulado",
        "anio": int(doc_id) if anual else None,
        "fecha_corte": datetime(2021, 12, 31, tzinfo=UTC)
        if anual
        else datetime(2024, 1, 17, tzinfo=UTC),
        "actualizado_en": datetime(2026, 11, 6, 10, 30, tzinfo=UTC),
        "casos_confirmados": 3_514_639 if anual else 6_390_971,
        "fallecidos": 96_017 if anual else 184_393,
        "recuperados": 3_379_222 if anual else 6_203_632,
        "activos": 39_400 if anual else 2_946,
        "tasa_letalidad": 0.027319 if anual else 0.028852,
        "tasa_recuperacion": 0.961471 if anual else 0.970654,
        "fuente": "casos_covid",
        "version_esquema": 2,
    }


def _override(documents: dict[str, dict[str, Any]]) -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "usr_ejecutivo_001",
        "role": "ejecutivo",
    }
    app.dependency_overrides[get_kpi_service] = lambda: KpiService(
        FakeKpiRepository(documents)
    )


def test_kpi_sin_token_devuelve_401() -> None:
    response = client.get("/api/v1/kpis/gerenciales")
    assert response.status_code == 401


def test_kpi_gerencial_devuelve_contrato() -> None:
    _override({"nacional": _document()})

    try:
        response = client.get("/api/v1/kpis/gerenciales")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "nacional"
    assert body["periodo"] == "acumulado"
    assert body["anio"] is None
    assert body["fecha_corte"] == "2024-01-17"
    assert body["kpis"]["casos_confirmados"] == 6_390_971
    assert body["kpis"]["activos"] == 2_946
    assert body["kpis"]["fallecidos"] == 184_393
    assert body["meta"]["fuente"] == "casos_covid"
    assert body["meta"]["version_esquema"] == 2
    assert response.headers["X-Process-Time"].endswith("ms")


def test_kpi_por_anio_devuelve_cohorte_historica() -> None:
    _override({"2021": _document("2021")})

    try:
        response = client.get("/api/v1/kpis/gerenciales?anio=2021")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["periodo"] == "anual"
    assert body["anio"] == 2021
    assert body["fecha_corte"] == "2021-12-31"
    assert body["kpis"]["casos_confirmados"] == 3_514_639
    assert body["kpis"]["activos"] == 39_400


def test_kpi_periodo_invalido_devuelve_400() -> None:
    _override({"nacional": _document()})

    try:
        response = client.get("/api/v1/kpis/gerenciales?anio=2019")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "acumulado" in response.json()["detail"]


def test_kpi_sin_documento_devuelve_503() -> None:
    _override({})

    try:
        response = client.get("/api/v1/kpis/gerenciales")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "no están disponibles" in response.json()["detail"]


def test_kpi_rol_no_autorizado_devuelve_403() -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "usr_desconocido",
        "role": "invitado",
    }

    try:
        response = client.get("/api/v1/kpis/gerenciales")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_fecha_corte_se_expone_como_fecha_iso() -> None:
    _override({"nacional": _document()})

    try:
        response = client.get("/api/v1/kpis/gerenciales")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert date.fromisoformat(response.json()["fecha_corte"]) == date(2024, 1, 17)


def test_to_document_convierte_date_de_parquet_a_datetime() -> None:
    document = _to_document({"fecha": date(2020, 1, 2), "id_caso": 1})
    assert isinstance(document["fecha"], datetime)
    assert document["fecha"].date() == date(2020, 1, 2)
