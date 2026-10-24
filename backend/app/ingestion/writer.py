"""Escritura incremental de Parquet particionado por año.

Se mantiene un ``ParquetWriter`` abierto por partición y cada chunk se escribe
como un row group nuevo. Así la memoria no depende del tamaño total del
dataset y no se generan miles de archivos pequeños.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def dataframe_to_arrow(df: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    """Convierte un DataFrame al esquema Arrow explícito de salida."""

    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.select(schema.names)
    return table.cast(schema)


class ParquetPartitionWriter:
    """Escribe DataFrames en archivos Parquet particionados por año."""

    def __init__(
        self,
        root: Path,
        schema: pa.Schema,
        *,
        filename: str = "casos.parquet",
        compression: str = "zstd",
        row_group_size: int = 100_000,
    ) -> None:
        self.root = Path(root)
        self.schema = schema
        self.filename = filename
        self.compression = compression
        self.row_group_size = row_group_size
        self.rows_written = 0
        self._writers: dict[int | None, pq.ParquetWriter] = {}

    def write(self, df: pd.DataFrame, *, partition: int | None) -> None:
        """Escribe ``df`` en la partición indicada (año o ``None``)."""

        if df.empty:
            return

        writer = self._writers.get(partition)
        if writer is None:
            if partition is None:
                directory = self.root
            else:
                directory = self.root / f"anio={partition}"
            directory.mkdir(parents=True, exist_ok=True)

            writer = pq.ParquetWriter(
                directory / self.filename,
                self.schema,
                compression=self.compression,
                use_dictionary=True,
            )
            self._writers[partition] = writer

        table = dataframe_to_arrow(df, self.schema)
        writer.write_table(
            table,
            row_group_size=min(len(table), self.row_group_size),
        )
        self.rows_written += len(table)

    def close(self) -> None:
        for writer in self._writers.values():
            writer.close()
        self._writers.clear()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
