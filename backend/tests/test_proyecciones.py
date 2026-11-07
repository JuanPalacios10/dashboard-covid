"""Pruebas del servicio y endpoint de proyecciones."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app
from app.services.dashboard import DepartamentoNotFoundError
from app.services.kpis import KpiService
from app.services.projections import (
    ProyeccionNotFoundError,
    ProyeccionService,
    ProyeccionValidationError,
    get_proyeccion_service,
)

client = TestClient(app)


class FakeDashboardRepository:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def get(self, doc_id: str) -> dict[str, Any] | None:
        return self.documents.get(doc_id)


class FakeKpiRepository:
    def get(self, doc_id: str) -> dict[str, Any] | None:
        return None


def _base_document(doc_id: str = "proyeccion:nacional:2021") -> dict[str, Any]:
    cutoff = date(2021, 12, 31)
    fechas = [
        (cutoff - timedelta(days=55 - index)).isoformat()
        for index in range(56)
    ]
    return {
        "_id": doc_id,
        "tipo": "nacional",
        "periodo": "anual",
        "anio": 2021,
        "fecha_corte": datetime(2021, 12, 31, tzinfo=UTC),
        "departamento": None,
        "calidad": {
            "nivel": "alta",
            "dias_base": 56,
            "dias_con_datos": 56,
            "mensaje": "Base de 56 días.",
        },
        "base": {
            "fechas": fechas,
            "casos_diarios": [10 + (index % 5) for index in range(56)],
            "activos_diarios": [80 + index for index in range(56)],
            "activos_al_corte": 135,
            "promedio_7d_actual": 12.0,
            "max_7d_periodo": 30.0,
            "r_estimado": 1.2,
        },
        "observado_posterior": {
            "fechas": ["2022-01-01", "2022-01-02"],
            "casos_diarios": [25, 30],
        },
    }


def _documents() -> dict[str, dict[str, Any]]:
    national = _base_document()
    department = _base_document("proyeccion:departamento:05:2021")
    department["tipo"] = "departamento"
    department["departamento"] = {"codigo": "05", "nombre": "ANTIOQUIA"}
    return {
        national["_id"]: national,
        department["_id"]: department,
        "territorios:2021": {
            "_id": "territorios:2021",
            "departamentos": [
                {"codigo": "05", "nombre": "ANTIOQUIA", "total": 100}
            ],
        },
    }


def _service(documents: dict[str, dict[str, Any]] | None = None) -> ProyeccionService:
    return ProyeccionService(
        FakeDashboardRepository(documents or _documents()),
        KpiService(FakeKpiRepository()),
    )


def _override(documents: dict[str, dict[str, Any]] | None = None) -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "usr_ejecutivo_001",
        "role": "ejecutivo",
    }
    app.dependency_overrides[get_proyeccion_service] = lambda: _service(documents)


def test_proyeccion_servicio_devuelve_cuatro_escenarios() -> None:
    payload = _service().get(
        periodo="2021",
        departamento=None,
        horizonte=60,
        r=1.3,
        medidas=40,
    )

    assert payload["periodo"] == "anual"
    assert payload["anio"] == 2021
    assert payload["calidad"]["nivel"] == "alta"
    assert payload["horizonte"] == 60
    assert len(payload["fechas_proyeccion"]) == 60
    assert len(payload["escenarios"]) == 4
    assert payload["escenarios"][-1]["id"] == "personalizado"
    assert payload["escenarios"][-1]["r_efectivo"] == pytest.approx(1.04)
    assert len(payload["escenarios"][-1]["nuevos"]) == 60
    assert payload["backtest"] is not None
    assert payload["backtest"]["dias_comparados"] == 2


def test_proyeccion_servicio_cambia_horizonte() -> None:
    payload = _service().get(
        periodo="2021",
        horizonte=30,
        medidas=40,
    )

    assert len(payload["fechas_proyeccion"]) == 30
    assert all(len(item["nuevos"]) == 30 for item in payload["escenarios"])
    assert all("nuevos_90d" in item["resumen"] for item in payload["escenarios"])


def test_proyeccion_servicio_horizonte_anual() -> None:
    payload = _service().get(
        periodo="2021",
        horizonte=365,
        medidas=40,
    )

    assert len(payload["fechas_proyeccion"]) == 365
    assert all(len(item["nuevos"]) == 365 for item in payload["escenarios"])
    assert all("nuevos_180d" in item["resumen"] for item in payload["escenarios"])
    assert all("nuevos_365d" in item["resumen"] for item in payload["escenarios"])
    assert payload["backtest"] is not None
    assert payload["backtest"]["observado_total"] >= 0
    assert payload["backtest"]["proyectado_total"] >= 0


def test_proyeccion_servicio_valida_parametros() -> None:
    with pytest.raises(ProyeccionValidationError):
        _service().get(periodo="2021", horizonte=45)
    with pytest.raises(ProyeccionValidationError):
        _service().get(periodo="2021", r=5)


def test_proyeccion_servicio_departamento_inexistente() -> None:
    with pytest.raises(DepartamentoNotFoundError):
        _service().get(periodo="2021", departamento="98")


def test_proyeccion_servicio_sin_documento() -> None:
    documents = _documents()
    documents.pop("proyeccion:nacional:2021")
    with pytest.raises(ProyeccionNotFoundError):
        _service(documents).get(periodo="2021")


def test_proyeccion_endpoint_sin_token_devuelve_401() -> None:
    response = client.get("/api/v1/proyecciones")
    assert response.status_code == 401


def test_proyeccion_endpoint_devuelve_contrato() -> None:
    _override()
    try:
        response = client.get(
            "/api/v1/proyecciones?anio=2021&horizonte=60&r=1.3&medidas=40"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["periodo"] == "anual"
    assert body["fecha_corte"] == "2021-12-31"
    assert len(body["escenarios"]) == 4
    assert body["base"]["activos_al_corte"] == 135
    assert body["backtest"]["dias_comparados"] == 2


def test_proyeccion_endpoint_horizonte_invalido_devuelve_400() -> None:
    _override()
    try:
        response = client.get("/api/v1/proyecciones?anio=2021&horizonte=45")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "horizonte" in response.json()["detail"].lower()


def test_proyeccion_endpoint_departamento_inexistente_devuelve_404() -> None:
    _override()
    try:
        response = client.get("/api/v1/proyecciones?anio=2021&departamento=98")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_proyeccion_endpoint_rol_no_autorizado_devuelve_403() -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "usr_desconocido",
        "role": "invitado",
    }
    app.dependency_overrides[get_proyeccion_service] = lambda: _service()
    try:
        response = client.get("/api/v1/proyecciones")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
