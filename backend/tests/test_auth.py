"""Pruebas de aceptación y unitarias para la autenticación y emisión de tokens JWT."""

from __future__ import annotations

import time
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import AuthService, InvalidCredentialsError

client = TestClient(app)


def test_login_exitoso_alfa_valida_jwt_rol_y_id() -> None:
    """Prueba de Aceptación Alfa: Inicio de sesión exitoso.

    Verifica que al enviar credenciales válidas:
    1. Responda HTTP 200 OK.
    2. Entregue access_token y token_type 'bearer'.
    3. Al decodificar el token, contenga sub='usr_94820' y role='admin'.
    4. Contenga claims iat y exp con vigencia futura.
    """
    payload = {
        "email": "usuario.prueba@dominio.com",
        "password": "PasswordValido123*",
    }

    response = client.post("/api/v1/auth/login", json=payload)

    # 1. Código 200 OK
    assert response.status_code == 200

    # 2. Estructura de respuesta
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    token = data["access_token"]
    assert isinstance(token, str) and len(token) > 0

    # 3. Decodificación y validación de claims
    service = AuthService()
    claims = service.decode_token(token)

    assert claims["sub"] == "usr_94820"
    assert claims["role"] == "admin"

    # 4. Vigencia temporal
    now = int(time.time())
    assert "iat" in claims
    assert "exp" in claims
    assert claims["exp"] > now


def test_login_contrasena_incorrecta_retorna_401() -> None:
    """Verifica que contraseñas incorrectas sean rechazadas con HTTP 401."""
    payload = {
        "email": "usuario.prueba@dominio.com",
        "password": "PasswordErronea999*",
    }

    response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas"


def test_login_usuario_inexistente_retorna_401() -> None:
    """Verifica que correos no registrados sean rechazados con HTTP 401."""
    payload = {
        "email": "no.existe@dominio.com",
        "password": "CualquierPassword123*",
    }

    response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas"


def test_auth_service_unitario() -> None:
    """Pruebas unitarias directas del servicio AuthService."""
    service = AuthService()

    # Usuario válido
    user = service.authenticate_user(
        "analista.prueba@dominio.com", "PasswordValido123*"
    )
    assert user["user_id"] == "usr_10204"
    assert user["role"] == "analista"

    # Token con rol analista
    token = service.create_access_token(
        user_id=user["user_id"],
        role=user["role"],
    )
    claims = service.decode_token(token)
    assert claims["sub"] == "usr_10204"
    assert claims["role"] == "analista"
