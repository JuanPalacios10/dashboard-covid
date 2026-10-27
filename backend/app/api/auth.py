"""Endpoints HTTP para autenticación y gestión de sesiones."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..services.auth import AuthService, InvalidCredentialsError, get_auth_service

router = APIRouter(prefix="/auth", tags=["autenticacion"])


class LoginRequest(BaseModel):
    """Esquema de entrada para solicitud de inicio de sesión."""

    email: str = Field(
        ...,
        examples=["usuario.prueba@dominio.com"],
        description="Correo electrónico registrado del usuario.",
    )
    password: str = Field(
        ...,
        examples=["PasswordValido123*"],
        description="Contraseña de acceso del usuario.",
    )


class TokenResponse(BaseModel):
    """Esquema de respuesta exitosa con token JWT."""

    access_token: str = Field(
        ...,
        description="Token de acceso JWT que codifica el ID y rol del usuario.",
    )
    token_type: str = Field(
        default="bearer",
        description="Tipo de token para el encabezado de autorización.",
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión y obtener token JWT con rol",
    description=(
        "Valida credenciales de usuario. Si son válidas retorna HTTP 200 con el JWT "
        "que codifica sub (ID) y role. Si son erróneas retorna HTTP 401 Unauthorized."
    ),
)
def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Procesa el inicio de sesión y entrega el token de acceso."""
    try:
        user = auth_service.authenticate_user(
            email=payload.email,
            password=payload.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    access_token = auth_service.create_access_token(
        user_id=user["user_id"],
        role=user["role"],
    )

    return TokenResponse(access_token=access_token, token_type="bearer")
