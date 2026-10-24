"""Deduplicación global de ``id_caso`` con memoria acotada.

En lugar de un ``set`` de Python (que consumiría cientos de MB para millones de
registros), se mantiene un arreglo ordenado de ``int64``. La pertenencia se
consulta con búsqueda binaria y la fusión se hace con ``numpy.unique``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class IdDeduplicator:
    """Detecta duplicados dentro y entre chunks conservando la primera fila.

    Los ids nuevos se acumulan en un búfer ordenado pequeño y solo se fusionan
    con el arreglo principal cada ``commit_threshold`` ids. Esto evita copiar
    decenas de MB en cada chunk y mantiene estable el uso de memoria.
    """

    def __init__(self, commit_threshold: int = 1_000_000) -> None:
        self._seen = np.empty(0, dtype=np.int64)
        self._pending = np.empty(0, dtype=np.int64)
        self._commit_threshold = max(int(commit_threshold), 1)
        self.duplicates = 0

    @property
    def seen_count(self) -> int:
        return int(self._seen.size + self._pending.size)

    @property
    def memory_bytes(self) -> int:
        return int(self._seen.nbytes + self._pending.nbytes)

    def mark_duplicates(self, ids: pd.Series | np.ndarray) -> np.ndarray:
        """Devuelve una máscara booleana con las filas duplicadas.

        Un id se considera duplicado si ya apareció en un chunk anterior o si
        se repite antes dentro del mismo arreglo.
        """

        values = np.asarray(ids, dtype=np.int64)
        if values.size == 0:
            return np.zeros(0, dtype=bool)

        already_seen = self._contains(values)

        # ``duplicated`` marca la segunda y posteriores ocurrencias dentro del
        # chunk; para las que ya existían, la deduplicación previa ya las marca.
        local_duplicates = pd.Series(values).duplicated(keep="first").to_numpy()
        duplicates = already_seen | local_duplicates

        new_values = values[~duplicates]
        if new_values.size:
            self._merge(new_values)

        self.duplicates += int(duplicates.sum())
        return duplicates

    def _contains(self, values: np.ndarray) -> np.ndarray:
        return self._contains_sorted(self._seen, values) | self._contains_sorted(
            self._pending, values
        )

    @staticmethod
    def _contains_sorted(sorted_values: np.ndarray, values: np.ndarray) -> np.ndarray:
        if sorted_values.size == 0:
            return np.zeros(values.size, dtype=bool)

        positions = np.searchsorted(sorted_values, values)
        positions = np.clip(positions, 0, sorted_values.size - 1)
        return sorted_values[positions] == values

    def _merge(self, new_values: np.ndarray) -> None:
        if self._pending.size == 0:
            self._pending = np.unique(new_values)
        else:
            self._pending = np.unique(
                np.concatenate((self._pending, new_values))
            )

        if self._pending.size >= self._commit_threshold:
            if self._seen.size == 0:
                self._seen, self._pending = self._pending, np.empty(
                    0, dtype=np.int64
                )
            else:
                self._seen = np.unique(
                    np.concatenate((self._seen, self._pending))
                )
                self._pending = np.empty(0, dtype=np.int64)

