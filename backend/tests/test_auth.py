"""Pruebas integrales y unitarias para autenticación JWT, MongoDB y RBAC."""

from __future__ import annotations

import time
import unittest
from typing import Any
from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.api.auth import (
    CreateUserRequest,
    LoginRequest,
    RegisterRequest,
    create_user,
    get_auth_service,
    get_current_user,
    get_me,
    login,
    register,
    require_roles,
)
from app.database import UserRepository
from app.main import app
from app.services.auth import (
    AuthenticationError,
    AuthService,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserRole,
)
from app.services.security import PasswordHasher
from scripts.create_user import DEFAULT_SEED_USERS, seed_default_users


def _build_mongo_collection_double() -> MagicMock:
    """Construye un doble de prueba de Collection de PyMongo que respalda consultas e índices."""
    store: dict[str, dict[str, Any]] = {}
    collection = MagicMock()

    def _find_one(
        filter_query: dict[str, Any], projection: dict[str, int] | None = None
    ) -> dict[str, Any] | None:
        for doc in store.values():
            if all(doc.get(k) == v for k, v in filter_query.items()):
                result = dict(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None

    def _insert_one(document: dict[str, Any]) -> MagicMock:
        email = document["email"]
        if email in store:
            from pymongo.errors import DuplicateKeyError

            raise DuplicateKeyError(f"E11000 duplicate key error: {email}")
        store[email] = dict(document)
        return MagicMock(inserted_id=document["user_id"])

    def _update_one(
        filter_query: dict[str, Any], update_doc: dict[str, Any]
    ) -> MagicMock:
        for doc in store.values():
            if all(doc.get(k) == v for k, v in filter_query.items()):
                if "$set" in update_doc:
                    doc.update(update_doc["$set"])
        return MagicMock(modified_count=1)

    collection.find_one.side_effect = _find_one
    collection.insert_one.side_effect = _insert_one
    collection.update_one.side_effect = _update_one
    return collection


class TestAuthAndRBAC(unittest.TestCase):
    """Pruebas de autenticación JWT, persistencia en repositorio MongoDB y control de roles."""

    def setUp(self) -> None:
        self.mock_collection = _build_mongo_collection_double()
        self.user_repo = UserRepository(collection=self.mock_collection)
        self.hasher = PasswordHasher(iterations=100_000)
        self.auth_service = AuthService(
            user_repository=self.user_repo,
            password_hasher=self.hasher,
            secret_key="test-secret-key-for-jwt-verification",
            token_expire_minutes=60,
        )

    def test_roles_definidos_admin_analista_ejecutivo(self) -> None:
        """Verifica que existan exactamente los 3 roles requeridos."""
        roles = {r.value for r in UserRole}
        self.assertEqual(roles, {"admin", "analista", "ejecutivo"})

    def test_seed_default_users_crea_admin_analista_ejecutivo(self) -> None:
        """Verifica que el script de semillado cree los 3 perfiles base con clave cifrada."""
        exit_code = seed_default_users(self.auth_service)
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(DEFAULT_SEED_USERS), 3)

        for spec in DEFAULT_SEED_USERS:
            stored = self.user_repo.get_by_email(spec["email"])
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored["role"], spec["role"].value)
            self.assertTrue(stored["hashed_password"].startswith("pbkdf2_sha256$"))
            self.assertNotEqual(stored["hashed_password"], spec["password"])

        # Segunda ejecución idempotente (no falla si ya existen)
        exit_code_2 = seed_default_users(self.auth_service)
        self.assertEqual(exit_code_2, 0)

    def test_login_exitoso_entrega_jwt_y_actualiza_last_login(self) -> None:
        """Prueba inicio de sesión exitoso, claims del JWT y actualización en MongoDB."""
        self.auth_service.create_user(
            user_id="usr_admin_001",
            email="admin@covid.com",
            password="AdminSeguro2026*",
            full_name="Administrador Principal",
            role=UserRole.ADMIN,
        )

        response = login(
            payload=LoginRequest(email="admin@covid.com", password="AdminSeguro2026*"),
            auth_service=self.auth_service,
        )

        self.assertEqual(response.token_type, "bearer")
        self.assertEqual(response.user.user_id, "usr_admin_001")
        self.assertEqual(response.user.role, UserRole.ADMIN)
        self.assertIsNotNone(response.user.last_login_at)

        claims = self.auth_service.decode_token(response.access_token)
        self.assertEqual(claims["sub"], "usr_admin_001")
        self.assertEqual(claims["role"], "admin")
        self.assertEqual(claims["email"], "admin@covid.com")
        self.assertGreater(claims["exp"], int(time.time()))

    def test_registro_publico_crea_usuario_y_entrega_token(self) -> None:
        """Verifica que /register cree el usuario con su rol y devuelva un JWT utilizable."""
        response = register(
            payload=RegisterRequest(
                email="nuevo.registro@covid.com",
                password="RegistroSeguro2026*",
                full_name="Usuario Registrado",
                role=UserRole.EJECUTIVO,
            ),
            auth_service=self.auth_service,
        )

        self.assertEqual(response.user.email, "nuevo.registro@covid.com")
        self.assertEqual(response.user.role, UserRole.EJECUTIVO)
        self.assertEqual(response.user.full_name, "Usuario Registrado")
        self.assertEqual(response.token_type, "bearer")

        claims = self.auth_service.decode_token(response.access_token)
        self.assertEqual(claims["sub"], response.user.user_id)
        self.assertEqual(claims["role"], "ejecutivo")

        stored = self.user_repo.get_by_email("nuevo.registro@covid.com")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertNotEqual(stored["hashed_password"], "RegistroSeguro2026*")

    def test_registro_duplicado_retorna_409_y_clave_debil_400(self) -> None:
        """Verifica los errores del auto-registro para correo duplicado y clave débil."""
        register(
            payload=RegisterRequest(
                email="duplicado@covid.com",
                password="RegistroSeguro2026*",
                full_name="Primer Registro",
                role=UserRole.ANALISTA,
            ),
            auth_service=self.auth_service,
        )

        with self.assertRaises(HTTPException) as ctx_dup:
            register(
                payload=RegisterRequest(
                    email="duplicado@covid.com",
                    password="OtroRegistro2026*",
                    full_name="Segundo Registro",
                    role=UserRole.ANALISTA,
                ),
                auth_service=self.auth_service,
            )
        self.assertEqual(ctx_dup.exception.status_code, 409)

        with self.assertRaises(HTTPException) as ctx_weak:
            register(
                payload=RegisterRequest(
                    email="clave.debil@covid.com",
                    password="sololetras",
                    full_name="Clave Débil",
                    role=UserRole.ANALISTA,
                ),
                auth_service=self.auth_service,
            )
        self.assertEqual(ctx_weak.exception.status_code, 400)

    def test_registro_endpoint_http_201_y_login_inmediato(self) -> None:
        """Prueba el contrato HTTP real de /auth/register y su uso posterior en /auth/login."""
        client = TestClient(app)
        app.dependency_overrides[get_auth_service] = lambda: self.auth_service

        try:
            register_response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "http.registro@covid.com",
                    "password": "RegistroHttp2026*",
                    "full_name": "Registro HTTP",
                    "role": "analista",
                },
            )
            self.assertEqual(register_response.status_code, 201)
            body = register_response.json()
            self.assertEqual(body["token_type"], "bearer")
            self.assertEqual(body["user"]["role"], "analista")
            self.assertTrue(body["access_token"])

            login_response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "http.registro@covid.com",
                    "password": "RegistroHttp2026*",
                },
            )
            self.assertEqual(login_response.status_code, 200)
            self.assertEqual(login_response.json()["user"]["email"], "http.registro@covid.com")
        finally:
            app.dependency_overrides.clear()

    def test_login_credenciales_invalidas_retorna_401(self) -> None:
        """Verifica que clave incorrecta o usuario inexistente lancen HTTP 401."""
        self.auth_service.create_user(
            email="analista@covid.com",
            password="AnalistaSeguro2026*",
            full_name="Analista Prueba",
            role=UserRole.ANALISTA,
        )

        # Contraseña errónea
        with self.assertRaises(HTTPException) as ctx_wrong_pwd:
            login(
                payload=LoginRequest(
                    email="analista@covid.com", password="PasswordErronea999*"
                ),
                auth_service=self.auth_service,
            )
        self.assertEqual(ctx_wrong_pwd.exception.status_code, 401)

        # Usuario inexistente
        with self.assertRaises(HTTPException) as ctx_no_user:
            login(
                payload=LoginRequest(
                    email="no.existe@covid.com", password="AnalistaSeguro2026*"
                ),
                auth_service=self.auth_service,
            )
        self.assertEqual(ctx_no_user.exception.status_code, 401)

    def test_solo_admin_puede_crear_usuarios_rbac(self) -> None:
        """Verifica que solo el rol 'admin' pueda crear usuarios; analista y ejecutivo reciben 403."""
        seed_default_users(self.auth_service)

        # 1. Login como admin, analista y ejecutivo
        admin_login = login(
            LoginRequest(email="admin@covid.com", password="AdminSeguro2026*"),
            auth_service=self.auth_service,
        )
        analista_login = login(
            LoginRequest(email="analista@covid.com", password="AnalistaSeguro2026*"),
            auth_service=self.auth_service,
        )
        ejecutivo_login = login(
            LoginRequest(email="ejecutivo@covid.com", password="EjecutivoSeguro2026*"),
            auth_service=self.auth_service,
        )

        admin_checker = require_roles([UserRole.ADMIN])

        # Validar usuario actual desde el token de admin
        admin_user = get_current_user(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=admin_login.access_token
            ),
            auth_service=self.auth_service,
        )
        verified_admin = admin_checker(current_user=admin_user)

        # Admin crea exitosamente un nuevo usuario ejecutivo
        created_response = create_user(
            payload=CreateUserRequest(
                email="nuevo.ejecutivo@covid.com",
                password="NuevoEjecutivo2026*",
                full_name="Nuevo Ejecutivo",
                role=UserRole.EJECUTIVO,
            ),
            _admin_user=verified_admin,
            auth_service=self.auth_service,
        )
        self.assertEqual(created_response.email, "nuevo.ejecutivo@covid.com")
        self.assertEqual(created_response.role, UserRole.EJECUTIVO)
        self.assertFalse(hasattr(created_response, "hashed_password"))

        # 2. Analista intenta pasar el guard de admin -> HTTP 403 Forbidden
        analista_user = get_current_user(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=analista_login.access_token
            ),
            auth_service=self.auth_service,
        )
        with self.assertRaises(HTTPException) as ctx_analista:
            admin_checker(current_user=analista_user)
        self.assertEqual(ctx_analista.exception.status_code, 403)

        # 3. Ejecutivo intenta pasar el guard de admin -> HTTP 403 Forbidden
        ejecutivo_user = get_current_user(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=ejecutivo_login.access_token
            ),
            auth_service=self.auth_service,
        )
        with self.assertRaises(HTTPException) as ctx_ejecutivo:
            admin_checker(current_user=ejecutivo_user)
        self.assertEqual(ctx_ejecutivo.exception.status_code, 403)

    def test_crear_usuario_duplicado_retorna_409_conflict(self) -> None:
        """Verifica que crear un usuario con un email ya existente retorne HTTP 409."""
        seed_default_users(self.auth_service)
        admin_doc = self.user_repo.get_by_email("admin@covid.com")
        assert admin_doc is not None

        with self.assertRaises(HTTPException) as ctx_dup:
            create_user(
                payload=CreateUserRequest(
                    email="analista@covid.com",
                    password="AnalistaSeguro2026*",
                    full_name="Analista Duplicado",
                    role=UserRole.ANALISTA,
                ),
                _admin_user=admin_doc,
                auth_service=self.auth_service,
            )
        self.assertEqual(ctx_dup.exception.status_code, 409)

    def test_endpoint_me_retorna_usuario_autenticado(self) -> None:
        """Verifica que GET /me retorne los datos públicos del usuario autenticado."""
        seed_default_users(self.auth_service)
        ejecutivo_login = login(
            LoginRequest(email="ejecutivo@covid.com", password="EjecutivoSeguro2026*"),
            auth_service=self.auth_service,
        )
        current = get_current_user(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=ejecutivo_login.access_token
            ),
            auth_service=self.auth_service,
        )
        profile = get_me(current_user=current)
        self.assertEqual(profile.email, "ejecutivo@covid.com")
        self.assertEqual(profile.role, UserRole.EJECUTIVO)


if __name__ == "__main__":
    unittest.main()
