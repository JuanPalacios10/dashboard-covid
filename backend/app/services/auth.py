"""Servicio de autenticación, gestión de usuarios y emisión de tokens JWT."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import jwt
from fastapi import Depends

from ..config import get_settings
from ..database import (
    DuplicateEntityError,
    UserRepository,
    UserRepositoryProtocol,
    get_user_repository,
)
from .security import PasswordHasher, WeakPasswordError

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """Roles autorizados dentro del sistema del Dashboard COVID-19."""

    ADMIN = "admin"
    ANALISTA = "analista"
    EJECUTIVO = "ejecutivo"


class AuthenticationError(Exception):
    """Excepción base para errores de autenticación y autorización."""


class InvalidCredentialsError(AuthenticationError):
    """Se lanza cuando el correo o la contraseña no coinciden con ningún registro válido."""


class UserInactiveError(AuthenticationError):
    """Se lanza cuando un usuario válido intenta operar con la cuenta deshabilitada."""


class UserAlreadyExistsError(AuthenticationError):
    """Se lanza cuando se intenta registrar un correo electrónico que ya existe."""


class InsufficientPermissionsError(AuthenticationError):
    """Se lanza cuando un usuario no posee el rol requerido para una acción."""


class AuthService:
    """Servicio que orquesta la autenticación, creación de usuarios y manejo de JWT."""

    def __init__(
        self,
        user_repository: UserRepositoryProtocol | None = None,
        password_hasher: PasswordHasher | None = None,
        secret_key: str | None = None,
        algorithm: str | None = None,
        token_expire_minutes: int | None = None,
    ) -> None:
        settings = get_settings()
        self.user_repository: UserRepositoryProtocol = (
            user_repository if user_repository is not None else UserRepository()
        )
        self.password_hasher: PasswordHasher = (
            password_hasher if password_hasher is not None else PasswordHasher()
        )
        self.secret_key: str = (
            secret_key if secret_key is not None else settings.jwt_secret_key
        )
        self.algorithm: str = (
            algorithm if algorithm is not None else settings.jwt_algorithm
        )
        self.token_expire_minutes: int = (
            token_expire_minutes
            if token_expire_minutes is not None
            else settings.jwt_access_token_expire_minutes
        )

    def authenticate_user(self, email: str, password: str) -> dict[str, Any]:
        """Valida las credenciales del usuario contra MongoDB y verifica el hash PBKDF2.

        Raises:
            InvalidCredentialsError: Si el usuario no existe o la contraseña no coincide.
            UserInactiveError: Si la cuenta del usuario está desactivada.
        """
        normalized_email = email.strip().lower()
        user = self.user_repository.get_by_email(normalized_email)

        if user is None:
            logger.info("Intento de login fallido: usuario no encontrado (%s)", normalized_email)
            raise InvalidCredentialsError("Credenciales inválidas")

        hashed_password = user.get("hashed_password", "")
        if not self.password_hasher.verify_password(password, hashed_password):
            logger.info("Intento de login fallido: contraseña incorrecta (%s)", normalized_email)
            raise InvalidCredentialsError("Credenciales inválidas")

        if not user.get("is_active", True):
            logger.warning("Intento de login en cuenta inactiva (%s)", normalized_email)
            raise UserInactiveError("La cuenta de usuario se encuentra inactiva.")

        self.user_repository.update_last_login(user["user_id"])
        user["last_login_at"] = datetime.now(timezone.utc)
        return user

    def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        role: UserRole | str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Crea un nuevo usuario validando complejidad de clave, rol y unicidad en MongoDB.

        Raises:
            WeakPasswordError: Si la contraseña no cumple las reglas de seguridad.
            ValueError: Si el rol no pertenece a UserRole.
            UserAlreadyExistsError: Si el correo ya se encuentra registrado.
        """
        role_enum = UserRole(role) if not isinstance(role, UserRole) else role
        normalized_email = email.strip().lower()
        clean_name = full_name.strip()

        if not normalized_email or "@" not in normalized_email:
            raise ValueError("El correo electrónico proporcionado no es válido.")

        self.password_hasher.validate_password_complexity(password)

        existing = self.user_repository.get_by_email(normalized_email)
        if existing is not None:
            raise UserAlreadyExistsError(
                f"Ya existe un usuario registrado con el correo '{normalized_email}'."
            )

        hashed_password = self.password_hasher.hash_password(password)
        now = datetime.now(timezone.utc)
        generated_id = user_id if user_id is not None else f"usr_{uuid.uuid4().hex[:12]}"

        user_doc: dict[str, Any] = {
            "user_id": generated_id,
            "email": normalized_email,
            "full_name": clean_name,
            "hashed_password": hashed_password,
            "role": role_enum.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }

        try:
            created = self.user_repository.create_user(user_doc)
        except DuplicateEntityError as exc:
            raise UserAlreadyExistsError(str(exc)) from exc

        logger.info(
            "Usuario creado exitosamente: user_id=%s email=%s role=%s",
            created["user_id"],
            created["email"],
            created["role"],
        )
        return created

    def create_access_token(
        self,
        user_id: str,
        role: str,
        email: str | None = None,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Genera un token JWT firmado (HS256) con claims sub, role, email, iat, exp y jti."""
        now = datetime.now(timezone.utc)
        expire = now + (
            expires_delta
            if expires_delta is not None
            else timedelta(minutes=self.token_expire_minutes)
        )

        payload: dict[str, Any] = {
            "sub": user_id,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "jti": uuid.uuid4().hex,
        }
        if email is not None:
            payload["email"] = email

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        """Decodifica y valida la firma y vigencia de un token JWT.

        Raises:
            AuthenticationError: Si el token es inválido, fue alterado o expiró.
        """
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"require": ["sub", "role", "exp", "iat"]},
            )
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("El token ha expirado.") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Token inválido: {exc}") from exc

    def get_current_user_from_token(self, token: str) -> dict[str, Any]:
        """Valida el token JWT y recupera el usuario activo desde MongoDB.

        Raises:
            AuthenticationError: Si el token es inválido o el usuario no existe.
            UserInactiveError: Si el usuario está deshabilitado.
        """
        claims = self.decode_token(token)
        user_id = claims.get("sub")
        if not user_id or not isinstance(user_id, str):
            raise AuthenticationError("Token sin identificador de sujeto válido.")

        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("El usuario asociado al token no existe.")

        if not user.get("is_active", True):
            raise UserInactiveError("La cuenta de usuario se encuentra inactiva.")

        return user


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> AuthService:
    """Proveedor de dependencia de FastAPI para AuthService."""
    return AuthService(user_repository=user_repo)
