"""Monitor de memoria RAM del proceso de ingesta.

Lee ``/proc/self/statm`` cuando está disponible (Linux) y cae a
``resource.getrusage`` en otros sistemas. Un hilo ligero muestrea el uso para
poder reportar el pico real y abortar si se supera el umbral configurado.
"""

from __future__ import annotations

import os
import platform
import resource
import threading
from pathlib import Path

_PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
_STATM = Path("/proc/self/statm")
_IS_LINUX = platform.system() == "Linux"


class MemoryLimitExceeded(RuntimeError):
    """Se lanza cuando el proceso supera el umbral de memoria configurado."""


def _read_rss_bytes() -> int:
    """Devuelve la memoria residente actual del proceso en bytes."""

    try:
        fields = _STATM.read_text().split()
        return int(fields[1]) * _PAGE_SIZE
    except (OSError, IndexError, ValueError):
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reporta KiB; macOS reporta bytes.
        return int(usage) * 1024 if _IS_LINUX else int(usage)


def get_peak_rss_mb() -> float:
    """Pico de memoria residente reportado por el sistema operativo."""

    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = int(usage) * 1024 if _IS_LINUX else int(usage)
    return round(peak_bytes / (1024 * 1024), 2)


class MemoryMonitor:
    """Muestrea el uso de RAM y expone el pico observado."""

    def __init__(self, limit_mb: int, interval_seconds: float = 0.05) -> None:
        self.limit_mb = int(limit_mb)
        self.interval_seconds = interval_seconds
        self._peak_bytes = _read_rss_bytes()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._sample_loop, name="memory-monitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._sample()

    @property
    def current_mb(self) -> float:
        return round(_read_rss_bytes() / (1024 * 1024), 2)

    @property
    def peak_mb(self) -> float:
        with self._lock:
            return round(self._peak_bytes / (1024 * 1024), 2)

    def check(self) -> None:
        """Aborta si el uso actual o el pico superan el límite."""

        current = self.current_mb
        if current > self.limit_mb or self.peak_mb > self.limit_mb:
            raise MemoryLimitExceeded(
                f"Consumo de memoria {max(current, self.peak_mb):.1f} MB "
                f"supera el límite de {self.limit_mb} MB. "
                "Reduzca --chunk-size o aumente el umbral."
            )

    def _sample(self) -> None:
        current = _read_rss_bytes()
        with self._lock:
            self._peak_bytes = max(self._peak_bytes, current)

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()
