"""Configuración central del backend.

Los valores se pueden sobreescribir con variables de entorno con el prefijo
``COVID_`` o mediante un archivo ``backend/.env``. Ejemplos::

    COVID_DATASET_PATH=/ruta/al/dataset.csv
    COVID_CHUNK_SIZE=100000
    COVID_MEMORY_LIMIT_MB=1024
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Configuración de la aplicación."""

    model_config = SettingsConfigDict(
        env_prefix="COVID_",
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Dashboard COVID-19 API"
    app_version: str = "0.1.0"

    # Dataset de entrada.
    dataset_path: Path = BACKEND_DIR / "data" / "Casos_positivos_de_COVID-19_Colombia.csv"

    # Capa procesada (Parquet particionado por año).
    processed_dir: Path = BACKEND_DIR / "data" / "processed"

    # Ingesta.
    chunk_size: int = Field(default=100_000, ge=1_000)
    memory_limit_mb: int = Field(default=1_024, ge=128)
    parquet_compression: str = "zstd"
    deduplicate: bool = True

    # API.
    cors_origins: list[str] = ["*"]

    def ensure_directories(self) -> None:
        """Crea los directorios de datos que necesita la aplicación."""

        self.processed_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) de la aplicación."""

    return Settings()
