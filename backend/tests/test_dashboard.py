"""Pruebas del endpoint compuesto del tablero preagregado."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app
from app.services.dashboard import DashboardService, get_dashboard_service
from app.services.kpis import KpiService

client = TestClient(app)


class FakeDashboardRepository:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def get(self, doc_id: str) -> dict[str, Any] | None:
        return self.documents.get(doc_id)


class FakeKpiRepository:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def get(self, doc_id: str) -> dict[str, Any] | None:
        return self.documents.get(doc_id)


def _kpi_document() -> dict[str, Any]:
    return {
        "_id": "nacional",
        "scope": "nacional",
        "periodo": "acumulado",
        "anio": None,
        "fecha_corte": datetime(2024, 1, 17, tzinfo=UTC),
        "actualizado_en": datetime(2026, 11, 6, 10, 30, tzinfo=UTC),
        "casos_confirmados": 6_390_971,
        "fallecidos": 184_393,
        "recuperados": 6_203_632,
        "activos": 2_946,
        "tasa_letalidad": 0.028852,
        "tasa_recuperacion": 0.970654,
        "fuente": "casos_covid",
        "version_esquema": 2,
    }


def _dashboard_documents() -> dict[str, dict[str, Any]]:
    return {
        "series:nacional:acumulado": {
            "_id": "series:nacional:acumulado",
            "tipo": "nacional",
            "anio": None,
            "periodo": "acumulado",
            "granularidad": "mensual",
            "departamento": None,
            "fecha_corte": datetime(2024, 1, 17, tzinfo=UTC),
            "fechas": ["2020-03", "2020-04"],
            "series": [
                {
                    "codigo": "00",
                    "nombre": "Nacional",
                    "total": 10,
                    "valores": [4, 6],
                }
            ],
        },
        "series:departamento:05:acumulado": {
            "_id": "series:departamento:05:acumulado",
            "tipo": "departamento",
            "anio": None,
            "periodo": "acumulado",
            "granularidad": "mensual",
            "departamento": {"codigo": "05", "nombre": "ANTIOQUIA"},
            "fecha_corte": datetime(2024, 1, 17, tzinfo=UTC),
            "fechas": ["2020-03", "2020-04"],
            "series": [
                {
                    "codigo": "05001",
                    "nombre": "MEDELLIN",
                    "total": 10,
                    "valores": [4, 6],
                }
            ],
        },
        "territorios:acumulado": {
            "_id": "territorios:acumulado",
            "periodo": "acumulado",
            "anio": None,
            "fecha_corte": datetime(2024, 1, 17, tzinfo=UTC),
            "total": 10,
            "departamentos": [
                {
                    "codigo": "05",
                    "nombre": "ANTIOQUIA",
                    "total": 10,
                    "fallecidos": 1,
                    "tasa_letalidad": 0.1,
                    "participacion": 100.0,
                }
            ],
        },
        "demografia:acumulado": {
            "_id": "demografia:acumulado",
            "periodo": "acumulado",
            "anio": None,
            "fecha_corte": datetime(2024, 1, 17, tzinfo=UTC),
            "total": 10,
            "sexo": [
                {
                    "nombre": "Femenino",
                    "total": 5,
                    "fallecidos": 1,
                    "porcentaje": 50.0,
                    "tasa_letalidad": 0.2,
                }
            ],
            "edad": [
                {
                    "grupo": "0-9",
                    "total": 10,
                    "fallecidos": 1,
                    "porcentaje": 100.0,
                    "tasa_letalidad": 0.1,
                }
            ],
        },
        "heatmap:acumulado": {
            "_id": "heatmap:acumulado",
            "periodo": "acumulado",
            "anio": None,
            "fecha_corte": datetime(2024, 1, 17, tzinfo=UTC),
            "columnas": ["2020"],
            "filas": [
                {
                    "codigo": "05",
                    "nombre": "ANTIOQUIA",
                    "total": 10,
                    "valores": [10],
                }
            ],
        },
    }


def _override(
    *,
    dashboard_documents: dict[str, dict[str, Any]] | None = None,
    kpi_documents: dict[str, dict[str, Any]] | None = None,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "usr_ejecutivo_001",
        "role": "ejecutivo",
    }
    app.dependency_overrides[get_dashboard_service] = lambda: DashboardService(
        FakeDashboardRepository(
            dashboard_documents
            if dashboard_documents is not None
            else _dashboard_documents()
        ),
        KpiService(
            FakeKpiRepository(
                kpi_documents
                if kpi_documents is not None
                else {"nacional": _kpi_document()}
            )
        ),
    )


def test_dashboard_sin_token_devuelve_401() -> None:
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 401


def test_dashboard_nacional_devuelve_contrato() -> None:
    _override()

    try:
        response = client.get("/api/v1/dashboard?anio=acumulado")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["periodo"] == "acumulado"
    assert body["anio"] is None
    assert body["fecha_corte"] == "2024-01-17"
    assert body["kpis"]["activos"] == 2_946
    assert body["series"]["tipo"] == "nacional"
    assert body["territorios"]["departamentos"][0]["codigo"] == "05"
    assert body["demografia"]["edad"][0]["grupo"] == "0-9"
    assert body["heatmap"]["columnas"] == ["2020"]


def test_dashboard_departamento_devuelve_series_municipales() -> None:
    _override()

    try:
        response = client.get("/api/v1/dashboard?departamento=5")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["series"]["tipo"] == "departamento"
    assert body["series"]["departamento"]["codigo"] == "05"
    assert body["series"]["series"][0]["nombre"] == "MEDELLIN"


def test_dashboard_departamento_inexistente_devuelve_404() -> None:
    _override()

    try:
        response = client.get("/api/v1/dashboard?departamento=98")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "no existe" in response.json()["detail"]


def test_dashboard_periodo_invalido_devuelve_400() -> None:
    _override()

    try:
        response = client.get("/api/v1/dashboard?anio=2019")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_dashboard_servicio_expone_periodo_anual_para_un_anio() -> None:
    documents = {}
    for document in _dashboard_documents().values():
        updated = dict(document)
        updated["_id"] = updated["_id"].replace("acumulado", "2021")
        updated["periodo"] = "anual"
        updated["anio"] = 2021
        updated["fecha_corte"] = datetime(2021, 12, 31, tzinfo=UTC)
        documents[updated["_id"]] = updated

    kpi = _kpi_document()
    kpi.update(
        {
            "_id": "2021",
            "periodo": "anual",
            "anio": 2021,
            "fecha_corte": datetime(2021, 12, 31, tzinfo=UTC),
        }
    )
    service = DashboardService(
        FakeDashboardRepository(documents),
        KpiService(FakeKpiRepository({"2021": kpi})),
    )

    payload = service.get("2021")

    assert payload["periodo"] == "anual"
    assert payload["anio"] == 2021
    assert payload["series"]["anio"] == 2021


def test_dashboard_sin_agregados_devuelve_503() -> None:
    _override(dashboard_documents={})

    try:
        response = client.get("/api/v1/dashboard")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "Faltan agregados" in response.json()["detail"]
