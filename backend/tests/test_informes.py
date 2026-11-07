from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app
from app.services.dashboard import get_dashboard_service
from app.services.informes import build_informe_pdf_bytes, build_informe_report_hash

client = TestClient(app)


class FakeDashboardService:
    def get(self, periodo: str | None = None, departamento: str | None = None):
        return {
            'periodo': 'acumulado',
            'anio': None,
            'fecha_corte': '2024-01-17',
            'actualizado_en': '2026-11-06T10:30:00+00:00',
            'kpis': {
                'casos_confirmados': 6412380,
                'fallecidos': 180000,
                'recuperados': 6200000,
                'activos': 3200,
                'tasa_letalidad': 0.028,
                'tasa_recuperacion': 0.97,
            },
        }


def _override_executive() -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        'user_id': 'usr_ejecutivo_001',
        'role': 'ejecutivo',
        'email': 'ejecutivo@covid.com',
    }
    app.dependency_overrides[get_dashboard_service] = lambda: FakeDashboardService()


def test_exportar_pdf_requiere_rol_ejecutivo() -> None:
    _override_executive()
    response = client.post(
        '/api/v1/informes/pdf',
        json={
            'destino': 'Consejo de gobierno',
            'territorio': 'Nacional',
            'anio': 'acumulado',
            'incluir_proyeccion': True,
        },
    )
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/pdf')
    assert len(response.content) > 100


def test_exportar_pdf_sin_permiso_devuelve_403() -> None:
    app.dependency_overrides[get_current_user] = lambda: {
        'user_id': 'usr_analista_001',
        'role': 'analista',
        'email': 'analista@covid.com',
    }
    app.dependency_overrides[get_dashboard_service] = lambda: FakeDashboardService()

    response = client.post(
        '/api/v1/informes/pdf',
        json={'destino': 'Comité de emergencia', 'territorio': 'Nacional'},
    )
    assert response.status_code == 403


def test_pdf_hash_es_determinista_y_usa_territorio_seleccionado() -> None:
    payload = {
        'destino': 'Consejo de gobierno',
        'territorio': 'Antioquia',
        'anio': '2021',
        'departamento': '05',
        'incluir_proyeccion': True,
    }
    dashboard = {
        'kpis': {
            'casos_confirmados': 1000,
            'fallecidos': 12,
            'recuperados': 980,
            'activos': 8,
            'tasa_letalidad': 0.012,
            'tasa_recuperacion': 0.98,
        }
    }
    fixed_date = datetime(2026, 11, 7, 10, 15, tzinfo=timezone.utc)

    hash_a = build_informe_report_hash(payload, dashboard, fixed_date)
    hash_b = build_informe_report_hash(payload, dashboard, fixed_date)
    payload_distinta_territorio = {**payload, 'territorio': 'Bogotá'}
    hash_distinta_territorio = build_informe_report_hash(payload_distinta_territorio, dashboard, fixed_date)
    build_informe_pdf_bytes(payload, dashboard, fixed_date)

    assert hash_a == hash_b
    assert hash_a
    assert hash_a != hash_distinta_territorio


app.dependency_overrides.clear()
