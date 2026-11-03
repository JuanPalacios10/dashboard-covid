"""Pruebas unitarias para el módulo de seguridad y criptografía de contraseñas."""

from __future__ import annotations

import unittest

from app.services.security import (
    HASH_ALGORITHM_PREFIX,
    PasswordHasher,
    WeakPasswordError,
)


class TestPasswordSecurity(unittest.TestCase):
    """Suite de pruebas para hashing PBKDF2-HMAC-SHA256 y complejidad de contraseñas."""

    def setUp(self) -> None:
        # Usamos 100_000 iteraciones en pruebas para mantener velocidad y validar formato real
        self.hasher = PasswordHasher(iterations=100_000)

    def test_hash_password_formato_y_salt_unico(self) -> None:
        """Verifica que el hash tenga el formato esperado y genere salts distintos cada vez."""
        raw = "ClaveSegura2026*"
        hash1 = self.hasher.hash_password(raw)
        hash2 = self.hasher.hash_password(raw)

        self.assertNotEqual(hash1, hash2)
        self.assertNotIn(raw, hash1)

        parts = hash1.split("$")
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0], HASH_ALGORITHM_PREFIX)
        self.assertEqual(parts[1], "100000")

    def test_verify_password_correcta_e_incorrecta(self) -> None:
        """Comprueba la verificación en tiempo constante para claves válidas e inválidas."""
        raw = "AdminSeguro2026*"
        hashed = self.hasher.hash_password(raw)

        self.assertTrue(self.hasher.verify_password(raw, hashed))
        self.assertFalse(self.hasher.verify_password("ClaveIncorrecta2026*", hashed))
        self.assertFalse(self.hasher.verify_password(raw, "formato$invalido"))
        self.assertFalse(self.hasher.verify_password(raw, "otro_alg$1000$abc$def"))

    def test_validate_password_complexity_exitoso(self) -> None:
        """Valida que contraseñas con al menos 8 caracteres, 1 letra y 1 número pasen."""
        self.hasher.validate_password_complexity("password1")
        self.hasher.validate_password_complexity("Admin2026")
        self.hasher.validate_password_complexity("covid19abc")

    def test_validate_password_complexity_rechaza_debiles(self) -> None:
        """Verifica que contraseñas sin los requisitos mínimos lancen WeakPasswordError."""
        weak_passwords = [
            "pass1",          # Menos de 8 caracteres
            "sololetrasxyz",  # Sin números
            "1234567890",     # Sin letras
        ]
        for pwd in weak_passwords:
            with self.subTest(password=pwd):
                with self.assertRaises(WeakPasswordError):
                    self.hasher.validate_password_complexity(pwd)


if __name__ == "__main__":
    unittest.main()

