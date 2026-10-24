"""Gestión del job de ingesta ejecutado en segundo plano por la API."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

from ..ingestion.pipeline import (
    IngestionAlreadyRunning,
    IngestionConfig,
    run_ingestion,
)


class IngestionJobManager:
    """Mantiene el estado de la última/actual ejecución de ingesta.

    El estado vive en memoria del proceso. El resultado durable es el
    manifiesto JSON escrito por el pipeline.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "estado": "inactivo",
            "run_id": None,
            "iniciado_en": None,
            "finalizado_en": None,
            "progreso": None,
            "manifiesto": None,
            "error": None,
        }
        self._thread: threading.Thread | None = None

    def start(self, config: IngestionConfig) -> dict[str, Any]:
        with self._lock:
            if self._state["estado"] == "en_ejecucion":
                raise IngestionAlreadyRunning(
                    "Ya hay una ingesta en ejecución. Consulte /api/v1/ingesta/estado."
                )

            self._state = {
                "estado": "en_ejecucion",
                "run_id": None,
                "iniciado_en": datetime.now(UTC).isoformat(),
                "finalizado_en": None,
                "progreso": {
                    "chunks_procesados": 0,
                    "filas_leidas": 0,
                    "filas_validas": 0,
                    "filas_rechazadas": 0,
                },
                "manifiesto": None,
                "error": None,
            }

            self._thread = threading.Thread(
                target=self._execute,
                args=(config,),
                name="covid-ingestion",
                daemon=True,
            )
            self._thread.start()
            return dict(self._state)

    def _execute(self, config: IngestionConfig) -> None:
        try:
            manifest = run_ingestion(config, progress_callback=self._on_progress)
            with self._lock:
                self._state.update(
                    {
                        "estado": "completado",
                        "run_id": manifest["run_id"],
                        "finalizado_en": datetime.now(UTC).isoformat(),
                        "progreso": {
                            "chunks_procesados": manifest.get("chunks_procesados", 0),
                            "filas_leidas": manifest["totales"]["rows_read"],
                            "filas_validas": manifest["totales"]["rows_clean"],
                            "filas_rechazadas": manifest["totales"]["rows_rejected"],
                        },
                        "manifiesto": manifest.get("manifiesto"),
                        "error": None,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - se reporta al cliente
            with self._lock:
                self._state.update(
                    {
                        "estado": "fallido",
                        "finalizado_en": datetime.now(UTC).isoformat(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    def _on_progress(self, progress: dict[str, object]) -> None:
        with self._lock:
            self._state["run_id"] = progress.get("run_id")
            self._state["progreso"] = progress

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)
