"""Endpoints HTTP para autenticación, gestión de usuarios y control de acceso basado en roles (RBAC)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ..services.auth import (
    AuthenticationError,
    AuthService,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserInactiveError,
    UserRole,
    get_auth_service,
)
from ..services.security import WeakPasswordError

router = APIRouter(prefix="/auth", tags=["autenticacion"])
bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """Esquema de entrada para solicitud de inicio de sesión."""

    email: str = Field(
        ...,
        examples=["admin@covid.com"],
        description="Correo electrónico registrado del usuario.",
    )
    password: str = Field(
        ...,
        examples=["AdminSeguro2026*"],
        description="Contraseña de acceso del usuario.",
    )


class CreateUserRequest(BaseModel):
    """Esquema de entrada para creación de usuarios (exclusivo para administradores)."""

    email: str = Field(
        ...,
        examples=["analista.nuevo@covid.com"],
        description="Correo electrónico único del nuevo usuario.",
    )
    password: str = Field(
        ...,
        min_length=8,
        examples=["ClaveSegura2026*"],
        description="Contraseña en texto plano que será validada y cifrada con PBKDF2-SHA256.",
    )
    full_name: str = Field(
        ...,
        min_length=2,
        examples=["María Gómez"],
        description="Nombre completo del usuario.",
    )
    role: UserRole = Field(
        ...,
        examples=[UserRole.ANALISTA],
        description="Rol asignado en el sistema: 'admin', 'analista' o 'ejecutivo'.",
    )


class RegisterRequest(BaseModel):
    """Esquema de entrada para el auto-registro de usuarios desde el frontend."""

    email: str = Field(
        ...,
        examples=["nuevo.usuario@covid.com"],
        description="Correo electrónico único del nuevo usuario.",
    )
    password: str = Field(
        ...,
        min_length=8,
        examples=["ClaveSegura2026*"],
        description="Contraseña en texto plano que será validada y cifrada con PBKDF2-SHA256.",
    )
    full_name: str = Field(
        ...,
        min_length=2,
        examples=["María Gómez"],
        description="Nombre completo del usuario.",
    )
    role: UserRole = Field(
        default=UserRole.ANALISTA,
        examples=[UserRole.ANALISTA],
        description="Rol solicitado: 'admin', 'analista' o 'ejecutivo'.",
    )


class UserResponse(BaseModel):
    """Esquema público de salida para información de usuario (excluye credenciales)."""

    user_id: str = Field(..., description="Identificador único del usuario.")
    email: str = Field(..., description="Correo electrónico normalizado.")
    full_name: str = Field(..., description="Nombre completo del usuario.")
    role: UserRole = Field(..., description="Rol del usuario en la plataforma.")
    is_active: bool = Field(..., description="Estado de activación de la cuenta.")
    created_at: datetime | None = Field(default=None, description="Fecha de creación.")
    last_login_at: datetime | None = Field(
        default=None, description="Fecha del último inicio de sesión."
    )


class TokenResponse(BaseModel):
    """Esquema de respuesta exitosa al autenticarse con token JWT."""

    access_token: str = Field(
        ...,
        description="Token de acceso JWT firmado (HS256) con sub, role y vigencia.",
    )
    token_type: str = Field(
        default="bearer",
        description="Esquema de autorización HTTP.",
    )
    user: UserResponse = Field(
        ...,
        description="Perfil del usuario autenticado.",
    )


def _to_user_response(user_doc: dict[str, Any]) -> UserResponse:
    """Convierte un documento interno de usuario al esquema seguro de salida."""
    return UserResponse(
        user_id=user_doc["user_id"],
        email=user_doc["email"],
        full_name=user_doc.get("full_name", ""),
        role=UserRole(user_doc["role"]),
        is_active=user_doc.get("is_active", True),
        created_at=user_doc.get("created_at"),
        last_login_at=user_doc.get("last_login_at"),
    )


def _build_token_response(auth_service: AuthService, user_doc: dict[str, Any]) -> TokenResponse:
    """Genera el token JWT y la respuesta de autenticación para un usuario válido."""
    access_token = auth_service.create_access_token(
        user_id=user_doc["user_id"],
        role=user_doc["role"],
        email=user_doc["email"],
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=_to_user_response(user_doc),
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    """Dependencia FastAPI que valida el token Bearer y retorna el usuario activo."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Se requiere token Bearer.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return auth_service.get_current_user_from_token(credentials.credentials)
    except UserInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_roles(allowed_roles: list[UserRole]) -> Callable[..., dict[str, Any]]:
    """Generador de dependencias para restringir endpoints a una lista de roles permitidos."""
    allowed_values = {role.value for role in allowed_roles}

    def _role_checker(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes para realizar esta operación.",
            )
        return current_user

    return _role_checker


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión y obtener token JWT",
    description=(
        "Valida las credenciales contra MongoDB utilizando verificación PBKDF2-HMAC-SHA256. "
        "Retorna HTTP 200 con el token JWT y perfil del usuario, o HTTP 401 si son inválidas."
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
    except UserInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return _build_token_response(auth_service, user)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrarse y obtener token JWT",
    description=(
        "Crea un nuevo usuario en MongoDB con el rol indicado y devuelve el token JWT "
        "para que el frontend pueda iniciar la sesión inmediatamente. "
        "La contraseña debe tener al menos 8 caracteres, una letra y un número."
    ),
)
def register(
    payload: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Registra un usuario y entrega el token de acceso de forma inmediata."""
    try:
        user = auth_service.create_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return _build_token_response(auth_service, user)


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nuevo usuario (Solo Admin)",
    description=(
        "Registra un nuevo usuario en MongoDB con rol 'admin', 'analista' o 'ejecutivo'. "
        "Este endpoint está restringido exclusivamente a usuarios autenticados con rol 'admin'."
    ),
)
def create_user(
    payload: CreateUserRequest,
    _admin_user: dict[str, Any] = Depends(require_roles([UserRole.ADMIN])),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Crea un usuario en la base de datos previa validación de rol administrador."""
    try:
        created_user = auth_service.create_user(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return _to_user_response(created_user)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener perfil del usuario autenticado",
    description="Devuelve los datos del usuario asociado al token JWT enviado en el header Authorization.",
)
def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserResponse:
    """Retorna el perfil del usuario en sesión."""
    return _to_user_response(current_user)
