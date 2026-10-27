"""Dependencias de autenticación y autorización basadas en JWT."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..services.auth import AuthService, AuthenticationError, get_auth_service

security = HTTPBearer(auto_error=False)


class AuthenticatedUser(dict):
    """Representación del usuario autenticado extraída del token."""

    pass


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """Extrae y valida el token JWT desde el header Authorization.

    Lanza HTTP 401 si el token está ausente, malformado, alterado o expirado.
    """
    if credentials is None or not credentials.scheme or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    if not token or token.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = auth_service.decode_token(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub") or payload.get("user_id") or payload.get("id")
    role = payload.get("role") or payload.get("roles") or payload.get("rol")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Normalizar rol a string simple
    if isinstance(role, list) and role:
        role = role[0]
    role_str = str(role).lower()

    user = {
        "user_id": str(user_id),
        "role": role_str,
        "payload": payload,
    }
    request.state.user = user
    return user


def require_roles(*allowed_roles: str):
    """Dependencia que exige que el usuario autenticado tenga alguno de los roles permitidos.

    Lanza HTTP 403 si el rol no está autorizado.
    """

    allowed = {str(r).lower() for r in allowed_roles}

    def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_role = str(current_user.get("role", "")).lower()
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado",
            )
        return current_user

    return role_checker


require_admin = require_roles("admin", "administrador")
require_any_authenticated = get_current_user
