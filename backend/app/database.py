"""Capa de persistencia, gestión de conexiones MongoDB y repositorios de datos."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config import get_settings

logger = logging.getLogger(__name__)

_mongo_client: MongoClient[dict[str, Any]] | None = None


class DatabaseError(Exception):
    """Excepción base para errores de persistencia en la base de datos."""


class DuplicateEntityError(DatabaseError):
    """Se lanza cuando se intenta insertar un registro que viola un índice único."""


def get_mongo_client() -> MongoClient[dict[str, Any]]:
    """Obtiene o inicializa la instancia compartida de MongoClient."""
    global _mongo_client
    if _mongo_client is None:
        settings = get_settings()
        _mongo_client = MongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=5_000,
            connectTimeoutMS=5_000,
        )
    return _mongo_client


def get_mongo_db() -> Database[dict[str, Any]]:
    """Retorna la base de datos configurada en MongoDB."""
    settings = get_settings()
    client = get_mongo_client()
    return client[settings.mongo_database]


def close_mongo_client() -> None:
    """Cierra limpiamente la conexión activa de MongoDB."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None


class UserRepositoryProtocol(Protocol):
    """Contrato para el repositorio de usuarios (Principio de Inversión de Dependencias)."""

    def ensure_indexes(self) -> None:
        """Garantiza la existencia de los índices requeridos en la colección."""
        ...

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Busca un usuario por su correo electrónico normalizado."""
        ...

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Busca un usuario por su identificador único."""
        ...

    def create_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        """Inserta un nuevo usuario en la base de datos."""
        ...

    def update_last_login(self, user_id: str) -> None:
        """Actualiza la marca temporal del último inicio de sesión."""
        ...


class UserRepository:
    """Repositorio MongoDB para la gestión de usuarios y credenciales."""

    def __init__(self, collection: Collection[dict[str, Any]] | None = None) -> None:
        if collection is not None:
            self.collection = collection
        else:
            settings = get_settings()
            db = get_mongo_db()
            self.collection = db[settings.mongo_users_collection]

    def ensure_indexes(self) -> None:
        """Crea índices únicos sobre email y user_id en la colección de usuarios."""
        try:
            self.collection.create_index([("email", ASCENDING)], unique=True)
            self.collection.create_index([("user_id", ASCENDING)], unique=True)
        except PyMongoError as exc:
            logger.error("Error al asegurar índices en la colección de usuarios: %s", exc)
            raise DatabaseError("No se pudieron inicializar los índices de usuarios.") from exc

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Recupera un documento de usuario a partir de su correo electrónico."""
        normalized_email = email.strip().lower()
        try:
            doc = self.collection.find_one({"email": normalized_email}, {"_id": 0})
            return dict(doc) if doc is not None else None
        except PyMongoError as exc:
            logger.error("Error consultando usuario por email en MongoDB: %s", exc)
            raise DatabaseError("Error al consultar la base de datos de usuarios.") from exc

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Recupera un documento de usuario a partir de su user_id."""
        try:
            doc = self.collection.find_one({"user_id": user_id}, {"_id": 0})
            return dict(doc) if doc is not None else None
        except PyMongoError as exc:
            logger.error("Error consultando usuario por ID en MongoDB: %s", exc)
            raise DatabaseError("Error al consultar la base de datos de usuarios.") from exc

    def create_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        """Persiste un nuevo usuario en MongoDB garantizando unicidad."""
        document = dict(user_data)
        document["email"] = document["email"].strip().lower()
        try:
            self.ensure_indexes()
            self.collection.insert_one(document)
            document.pop("_id", None)
            return document
        except DuplicateKeyError as exc:
            raise DuplicateEntityError(
                f"Ya existe un usuario registrado con el correo '{document['email']}'."
            ) from exc
        except PyMongoError as exc:
            logger.error("Error insertando usuario en MongoDB: %s", exc)
            raise DatabaseError("No fue posible registrar el usuario en la base de datos.") from exc

    def update_last_login(self, user_id: str) -> None:
        """Actualiza el campo last_login_at y updated_at del usuario tras autenticarse."""
        now = datetime.now(timezone.utc)
        try:
            self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"last_login_at": now, "updated_at": now}},
            )
        except PyMongoError as exc:
            logger.warning(
                "No se pudo actualizar last_login_at para el usuario %s: %s",
                user_id,
                exc,
            )


def get_user_repository() -> UserRepository:
    """Proveedor de dependencia para obtener el repositorio de usuarios."""
    return UserRepository()
