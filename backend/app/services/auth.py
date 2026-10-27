"""Servicio de autenticación y gestión de tokens JWT (Prototipo Alfa)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import jwt
except ImportError:
    jwt = None  # Fallback a implementación nativa con HMAC-SHA256


class AuthenticationError(Exception):
    """Excepción base para errores de autenticación."""


class InvalidCredentialsError(AuthenticationError):
    """Se lanza cuando las credenciales no son válidas o el usuario no existe."""


# Usuarios en memoria para la prueba de aceptación alfa
ALFA_TEST_USERS: dict[str, dict[str, str]] = {
    "usuario.prueba@dominio.com": {
        "user_id": "usr_94820",
        "password": "PasswordValido123*",
        "role": "admin",
    },
    "analista.prueba@dominio.com": {
        "user_id": "usr_10204",
        "password": "PasswordValido123*",
        "role": "analista",
    },
}

DEFAULT_SECRET_KEY: str = "dashboard-covid-secret-key-alpha-prototype"
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60


def _b64url_encode(data: bytes) -> str:
    """Codifica bytes a base64url sin padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    """Decodifica un string base64url agregando el padding necesario."""
    padding = 4 - (len(data) % 4)
    if padding and padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class AuthService:
    """Servicio que encapsula la lógica de autenticación y emisión de JWT."""

    def __init__(
        self,
        users_db: dict[str, dict[str, str]] | None = None,
        secret_key: str = DEFAULT_SECRET_KEY,
        algorithm: str = ALGORITHM,
        token_expire_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES,
    ) -> None:
        self.users_db = users_db if users_db is not None else ALFA_TEST_USERS
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.token_expire_minutes = token_expire_minutes

    def authenticate_user(self, email: str, password: str) -> dict[str, str]:
        """Valida las credenciales del usuario contra el almacén de datos.

        Raises:
            InvalidCredentialsError: Si el correo no existe o la contraseña no coincide.
        """
        user = self.users_db.get(email.strip().lower())
        if not user or user["password"] != password:
            raise InvalidCredentialsError("Credenciales inválidas")
        return user

    def create_access_token(
        self,
        user_id: str,
        role: str,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Genera un token JWT firmado (HS256) con claims sub, role, iat y exp."""
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
        }

        if jwt is not None:
            return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        # Fallback nativo HS256 utilizando standard library
        header = {"alg": self.algorithm, "typ": "JWT"}
        header_b64 = _b64url_encode(
            json.dumps(header, separators=(",", ":")).encode("utf-8")
        )
        payload_b64 = _b64url_encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        sig_b64 = _b64url_encode(signature)
        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def decode_token(self, token: str) -> dict[str, Any]:
        """Decodifica y valida un token JWT.

        Raises:
            AuthenticationError: Si el token está expirado, alterado o es inválido.
        """
        if jwt is not None:
            try:
                return jwt.decode(
                    token,
                    self.secret_key,
                    algorithms=[self.algorithm],
                )
            except jwt.PyJWTError as exc:
                raise AuthenticationError(f"Token inválido o expirado: {exc}") from exc

        # Validación fallback nativa
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("Formato de token inválido")

        header_b64, payload_b64, sig_b64 = parts
        expected_sig = _b64url_encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                f"{header_b64}.{payload_b64}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(sig_b64, expected_sig):
            raise AuthenticationError("Firma del token no válida")

        try:
            payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        except Exception as exc:
            raise AuthenticationError("No se pudo decodificar el payload") from exc

        if "exp" in payload and time.time() > payload["exp"]:
            raise AuthenticationError("El token ha expirado")

        return payload


def get_auth_service() -> AuthService:
    """Proveedor del servicio de autenticación."""
    return AuthService()
