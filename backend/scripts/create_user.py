#!/usr/bin/env python
"""Script CLI para aprovisionar usuarios o sembrar los perfiles base en MongoDB.

Ejemplos::

    # Sembrar los 3 usuarios de prueba (admin, analista y ejecutivo):
    python backend/scripts/create_user.py --seed

    # Crear un usuario específico manualmente:
    python backend/scripts/create_user.py \\
        --email admin.custom@covid.com \\
        --password "AdminCustom2026*" \\
        --name "Administrador General" \\
        --role admin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import DatabaseError, close_mongo_client
from app.services.auth import AuthService, UserAlreadyExistsError, UserRole
from app.services.security import WeakPasswordError

DEFAULT_SEED_USERS: list[dict[str, Any]] = [
    {
        "user_id": "usr_admin_001",
        "email": "admin@covid.com",
        "password": "AdminSeguro2026*",
        "full_name": "Administrador Principal",
        "role": UserRole.ADMIN,
    },
    {
        "user_id": "usr_analista_001",
        "email": "analista@covid.com",
        "password": "AnalistaSeguro2026*",
        "full_name": "Analista Epidemiológico",
        "role": UserRole.ANALISTA,
    },
    {
        "user_id": "usr_ejecutivo_001",
        "email": "ejecutivo@covid.com",
        "password": "EjecutivoSeguro2026*",
        "full_name": "Ejecutivo de Toma de Decisiones",
        "role": UserRole.EJECUTIVO,
    },
]


def parse_args() -> argparse.Namespace:
    """Parsea los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Gestión y semillado de usuarios en MongoDB para Dashboard COVID-19.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Siembra los 3 usuarios de prueba por defecto (admin, analista y ejecutivo).",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Correo electrónico del nuevo usuario.",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Contraseña del nuevo usuario (mínimo 8 caracteres, al menos 1 letra y 1 número).",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Usuario del Sistema",
        help="Nombre completo del usuario.",
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=[role.value for role in UserRole],
        default=UserRole.ADMIN.value,
        help="Rol del usuario a crear (admin, analista o ejecutivo).",
    )
    return parser.parse_args()


def seed_default_users(auth_service: AuthService) -> int:
    """Crea los 3 usuarios base (admin, analista y ejecutivo) si no existen."""
    print("Sembrando usuarios iniciales en MongoDB...")
    created_count = 0

    for user_spec in DEFAULT_SEED_USERS:
        try:
            created = auth_service.create_user(
                user_id=user_spec["user_id"],
                email=user_spec["email"],
                password=user_spec["password"],
                full_name=user_spec["full_name"],
                role=user_spec["role"],
            )
            created_count += 1
            print(
                f"  [CREADO]    rol={created['role']:<10} | "
                f"email={created['email']:<22} | user_id={created['user_id']}"
            )
        except UserAlreadyExistsError:
            print(
                f"  [EXISTENTE] rol={user_spec['role'].value:<10} | "
                f"email={user_spec['email']:<22} (omitido)"
            )

    print(f"\nProceso finalizado. Usuarios nuevos insertados: {created_count}/3.")
    return 0


def main() -> int:
    """Punto de entrada principal del script."""
    args = parse_args()
    auth_service = AuthService()

    try:
        if args.seed or (args.email is None and args.password is None):
            return seed_default_users(auth_service)

        if not args.email or not args.password:
            print(
                "Error: Para crear un usuario personalizado debe especificar --email y --password "
                "(o usar --seed para crear los usuarios de prueba).",
                file=sys.stderr,
            )
            return 2

        created = auth_service.create_user(
            email=args.email,
            password=args.password,
            full_name=args.name,
            role=UserRole(args.role),
        )
        print("Usuario creado exitosamente en MongoDB:")
        print(f"  ID:     {created['user_id']}")
        print(f"  Nombre: {created['full_name']}")
        print(f"  Email:  {created['email']}")
        print(f"  Rol:    {created['role']}")
        return 0

    except (WeakPasswordError, UserAlreadyExistsError, ValueError) as exc:
        print(f"Error de validación: {exc}", file=sys.stderr)
        return 1
    except DatabaseError as exc:
        print(f"Error de base de datos MongoDB: {exc}", file=sys.stderr)
        return 1
    finally:
        close_mongo_client()


if __name__ == "__main__":
    raise SystemExit(main())

