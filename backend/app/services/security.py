"""Servicios criptográficos para hashing y validación de credenciales."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

from ..config import get_settings

HASH_ALGORITHM_PREFIX = "pbkdf2_sha256"
SALT_BYTES = 32
DERIVED_KEY_BYTES = 32
MIN_PASSWORD_LENGTH = 8

_LETTER_RE = re.compile(r"[a-zA-Z]")
_DIGIT_RE = re.compile(r"\d")


class SecurityError(Exception):
    """Excepción base para errores de seguridad y criptografía."""


class WeakPasswordError(SecurityError):
    """Se lanza cuando una contraseña no cumple con la complejidad mínima requerida."""


class PasswordHasher:
    """Encapsula el cifrado y verificación segura de contraseñas mediante PBKDF2-HMAC-SHA256."""

    def __init__(self, iterations: int | None = None) -> None:
        settings = get_settings()
        self.iterations: int = (
            iterations
            if iterations is not None
            else settings.password_hash_iterations
        )

    @staticmethod
    def validate_password_complexity(password: str) -> None:
        """Valida los requisitos de la contraseña.

        Requisitos:
        - Al menos 8 caracteres de longitud.
        - Al menos 1 letra.
        - Al menos 1 número.

        Raises:
            WeakPasswordError: Si la contraseña no cumple alguno de los requisitos.
        """
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(
                f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
            )
        if not _LETTER_RE.search(password):
            raise WeakPasswordError(
                "La contraseña debe incluir al menos una letra."
            )
        if not _DIGIT_RE.search(password):
            raise WeakPasswordError(
                "La contraseña debe incluir al menos un número."
            )

    def hash_password(self, plain_password: str) -> str:
        """Genera un hash PBKDF2-HMAC-SHA256 con un salt aleatorio único.

        Formato de salida:
            ``pbkdf2_sha256$<iteraciones>$<salt_b64>$<hash_b64>``
        """
        salt = secrets.token_bytes(SALT_BYTES)
        derived_key = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            self.iterations,
            dklen=DERIVED_KEY_BYTES,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        hash_b64 = base64.b64encode(derived_key).decode("ascii")
        return f"{HASH_ALGORITHM_PREFIX}${self.iterations}${salt_b64}${hash_b64}"

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifica una contraseña en texto plano contra un hash almacenado en tiempo constante."""
        try:
            parts = hashed_password.split("$")
            if len(parts) != 4:
                return False

            algorithm, iterations_str, salt_b64, expected_hash_b64 = parts
            if algorithm != HASH_ALGORITHM_PREFIX:
                return False

            iterations = int(iterations_str)
            if iterations < 1:
                return False

            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected_hash = base64.b64decode(expected_hash_b64.encode("ascii"))
        except (ValueError, TypeError):
            return False

        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_hash),
        )
        return hmac.compare_digest(candidate_hash, expected_hash)

