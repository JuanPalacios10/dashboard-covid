"""Normalización y limpieza de un bloque (chunk) del dataset de COVID-19.

El objetivo es que cada fila quede con los 15 campos canónicos, con tipos
consistentes y con las reglas de calidad aplicadas, sin cargar el archivo
completo en memoria.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .dedupe import IdDeduplicator
from .schema import (
    DATE_COLUMNS,
    DEPARTAMENTOS_DANE,
    EDAD_MAXIMA,
    EDAD_MINIMA,
    FINAL_COLUMNS,
    RECUPERADO_LABELS,
    SEXO_LABELS,
    TIPO_CONTAGIO_LABELS,
)
from .stats import ChunkReport, count_values


def normalize_text(series: pd.Series) -> pd.Series:
    """Limpia texto: recorta, colapsa espacios, pasa a mayúsculas y vacía a NA."""

    normalized = (
        series.astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.upper()
    )
    return normalized.replace("", pd.NA)


def _digits_only(series: pd.Series) -> pd.Series:
    """Elimina separadores de miles (puntos, comas y espacios) de un código."""

    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"[.,\s]", "", regex=True)
    )


def _parse_dates(
    raw: pd.DataFrame,
    report: ChunkReport,
    today: date,
) -> dict[str, pd.Series]:
    """Convierte las columnas de fecha a ``datetime64`` y registra anomalías."""

    parsed_columns: dict[str, pd.Series] = {}
    for column in DATE_COLUMNS:
        text = (
            raw[column]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
        )
        parsed = pd.to_datetime(text, errors="coerce", format="mixed").dt.normalize()

        invalid = text.notna() & parsed.isna()
        if invalid.any():
            report.invalid[f"{column}_invalida"] = int(invalid.sum())

        valid_dates = parsed.dropna()
        if not valid_dates.empty:
            report.date_min[column] = valid_dates.min().date()
            report.date_max[column] = valid_dates.max().date()

        future = parsed > pd.Timestamp(today)
        if future.any():
            report.inconsistencies[f"{column}_futura"] = int(future.sum())

        parsed_columns[column] = parsed

    return parsed_columns


def _clean_department_codes(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Devuelve (código de 2 dígitos, máscara de filas válidas).

    Algunos registros traen el código del municipio en la columna del
    departamento, por ejemplo ``"8.001"`` (Barranquilla). En ese caso se toma
    el prefijo departamental del código municipal.
    """

    digits = _digits_only(raw)
    structurally_valid = digits.str.fullmatch(r"\d{1,5}", na=False)

    code = digits.where(structurally_valid)

    short = (code.str.len() <= 2).fillna(False)
    code = code.where(~short, code.str.zfill(2))

    long = code.str.len().between(3, 5).fillna(False)
    code = code.where(~long, code.str.zfill(5).str[:2])

    valid = (
        structurally_valid
        & code.notna()
        & code.str.fullmatch(r"\d{2}", na=False)
    )
    return code.where(valid), valid


def _clean_municipality_codes(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Devuelve (código DIVIPOLA de 5 dígitos, máscara de filas válidas)."""

    digits = _digits_only(raw)
    valid = digits.str.fullmatch(r"\d{1,5}", na=False)
    code = digits.where(valid).str.zfill(5)
    return code, valid


def _map_category(
    raw: pd.Series,
    labels: dict[str, str],
    report: ChunkReport,
    column: str,
) -> pd.Series:
    """Normaliza una columna categórica usando un diccionario de etiquetas."""

    normalized = normalize_text(raw)
    mapped = normalized.map(labels)

    unknown = normalized.notna() & mapped.isna()
    if unknown.any():
        report.invalid[column] = int(unknown.sum())
        # Se conserva el valor original (en formato título) para no perder
        # información cuando aparezca una categoría nueva en el dataset.
        mapped = mapped.fillna(normalized.str.title())

    return mapped.astype("string")


def clean_chunk(
    raw: pd.DataFrame,
    *,
    today: date | None = None,
    deduplicator: IdDeduplicator | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, ChunkReport]:
    """Limpia y valida un chunk.

    Parameters
    ----------
    raw:
        Bloque leído del archivo (CSV o JSON Lines). Debe venir renombrado con
        los nombres internos definidos en :mod:`app.ingestion.schema` (incluye
        ``_unidad_edad``).
    today:
        Fecha de referencia para detectar fechas futuras. Se inyecta en las
        pruebas para que sean deterministas.
    deduplicator:
        Si se entrega, se descartan los ``id_caso`` repetidos (dentro del chunk
        o en chunks anteriores) y se mueven a la salida de rechazados.

    Returns
    -------
    clean:
        Filas válidas con las 15 columnas finales.
    rejected:
        Filas descartadas, con la columna ``motivo_rechazo``.
    report:
        Métricas de calidad del bloque.
    """

    if today is None:
        today = pd.Timestamp.now().date()

    report = ChunkReport(rows_read=len(raw))
    report.raw_nulls.update(
        {str(column): int(value) for column, value in raw.isna().sum().items()}
    )

    df = raw.copy()

    # ------------------------------------------------------------------
    # Identificador del caso
    # ------------------------------------------------------------------
    id_text = df["id_caso"].astype("string").str.strip()
    id_number = pd.to_numeric(
        id_text.str.replace(r"[.,\s]", "", regex=True), errors="coerce"
    )
    id_valid = id_number.notna() & np.isfinite(id_number) & (id_number % 1 == 0)
    invalid_ids = int((~id_valid).sum())
    if invalid_ids:
        report.invalid["id_caso"] = invalid_ids
    df["id_caso"] = id_number.where(id_valid).astype("Int64")

    # ------------------------------------------------------------------
    # Fechas
    # ------------------------------------------------------------------
    for column, parsed in _parse_dates(raw, report, today).items():
        df[column] = parsed

    # ------------------------------------------------------------------
    # Edad: se expresa siempre en años cumplidos
    # ------------------------------------------------------------------
    unit = normalize_text(raw["_unidad_edad"])
    age_number = pd.to_numeric(raw["edad"], errors="coerce")
    age_in_years = age_number.astype("float64")

    is_months = unit.eq("2")
    is_days = unit.eq("3")
    age_in_years = age_in_years.mask(is_months, age_in_years / 12)
    age_in_years = age_in_years.mask(is_days, age_in_years / 365.25)

    age_floor = np.floor(age_in_years)
    age_valid = (
        age_in_years.notna()
        & np.isfinite(age_in_years)
        & (age_floor >= EDAD_MINIMA)
        & (age_floor <= EDAD_MAXIMA)
    )
    invalid_ages = int((~age_valid).sum())
    if invalid_ages:
        report.invalid["edad"] = invalid_ages
    report.corrections["edad_convertida_desde_meses"] = int(is_months.sum())
    report.corrections["edad_convertida_desde_dias"] = int(is_days.sum())

    valid_units = unit.isin(["1", "2", "3"])
    unknown_units = unit.notna() & ~valid_units
    if unknown_units.any():
        report.invalid["unidad_edad_desconocida"] = int(unknown_units.sum())

    df["edad"] = age_floor.where(age_valid).astype("Int64")

    # ------------------------------------------------------------------
    # Códigos DIVIPOLA y nombres territoriales
    # ------------------------------------------------------------------
    department_code, department_valid = _clean_department_codes(
        raw["codigo_divipola_departamento"]
    )
    municipality_code, municipality_valid = _clean_municipality_codes(
        raw["codigo_divipola_municipio"]
    )

    if (~department_valid).any():
        report.invalid["codigo_divipola_departamento"] = int((~department_valid).sum())
    if (~municipality_valid).any():
        report.invalid["codigo_divipola_municipio"] = int(
            (~municipality_valid).sum()
        )

    municipality_prefix = municipality_code.str[:2]
    different_codes = (municipality_prefix != department_code).fillna(False)
    prefix_mismatch = (
        municipality_valid
        & department_valid
        & municipality_prefix.notna()
        & different_codes
    )
    if prefix_mismatch.any():
        report.inconsistencies["municipio_no_coincide_departamento"] = int(
            prefix_mismatch.sum()
        )

    department_name = normalize_text(raw["nombre_departamento"])
    canonical_name = department_code.map(DEPARTAMENTOS_DANE)
    known_department = department_code.notna() & canonical_name.notna()

    different_names = (canonical_name != department_name).fillna(False)
    renamed_departments = (
        known_department & department_name.notna() & different_names
    )
    if renamed_departments.any():
        report.corrections["nombre_departamento"] = int(renamed_departments.sum())

    unknown_department_codes = department_code.notna() & canonical_name.isna()
    if unknown_department_codes.any():
        report.invalid["codigo_departamento_desconocido"] = int(
            unknown_department_codes.sum()
        )

    df["codigo_divipola_departamento"] = department_code
    df["nombre_departamento"] = canonical_name.fillna(department_name).astype("string")
    df["codigo_divipola_municipio"] = municipality_code
    df["nombre_municipio"] = normalize_text(raw["nombre_municipio"])

    # ------------------------------------------------------------------
    # Categorías
    # ------------------------------------------------------------------
    df["sexo"] = _map_category(raw["sexo"], SEXO_LABELS, report, "sexo")
    df["tipo_contagio"] = _map_category(
        raw["tipo_contagio"], TIPO_CONTAGIO_LABELS, report, "tipo_contagio"
    )
    df["recuperado"] = _map_category(
        raw["recuperado"], RECUPERADO_LABELS, report, "recuperado"
    )

    # ------------------------------------------------------------------
    # Reglas de rechazo (la fila no se puede cargar de forma confiable)
    # ------------------------------------------------------------------
    rejection_rules = (
        (df["id_caso"].isna(), "id_caso inválido"),
        (df["fecha_reporte_web"].isna(), "fecha_reporte_web inválida"),
        (
            df["codigo_divipola_departamento"].isna(),
            "código DIVIPOLA departamento inválido",
        ),
        (
            df["codigo_divipola_municipio"].isna(),
            "código DIVIPOLA municipio inválido",
        ),
        (df["edad"].isna(), "edad inválida"),
    )

    rejection_code = np.zeros(len(df), dtype=np.int16)
    for bit, (mask, _reason) in enumerate(rejection_rules):
        rejection_code |= mask.to_numpy(dtype=bool).astype(np.int16) << bit
    rejected_mask = rejection_code > 0
    df["motivo_rechazo"] = pd.Series(pd.NA, index=df.index, dtype="string")

    if rejected_mask.any():
        reason_labels = [reason for _mask, reason in rejection_rules]
        motives = [
            "; ".join(
                reason_labels[bit]
                for bit in range(len(reason_labels))
                if value & (1 << bit)
            )
            for value in rejection_code[rejected_mask]
        ]
        df.loc[rejected_mask, "motivo_rechazo"] = motives

        for motive in motives:
            report.rejected_reasons.update(motive.split("; "))

    rejected = df.loc[
        rejected_mask, list(FINAL_COLUMNS) + ["motivo_rechazo"]
    ].copy()
    clean = df.loc[~rejected_mask, list(FINAL_COLUMNS)].copy()

    # ------------------------------------------------------------------
    # Deduplicación global por id_caso
    # ------------------------------------------------------------------
    if deduplicator is not None and not clean.empty:
        ids = clean["id_caso"].to_numpy(dtype=np.int64)
        duplicate_mask = deduplicator.mark_duplicates(ids)
        if duplicate_mask.any():
            duplicate_rows = clean.loc[duplicate_mask].copy()
            duplicate_rows["motivo_rechazo"] = "id_caso duplicado"
            rejected = pd.concat(
                [rejected, duplicate_rows], ignore_index=True
            )[list(FINAL_COLUMNS) + ["motivo_rechazo"]]
            clean = clean.loc[~duplicate_mask].reset_index(drop=True)

            duplicates = int(duplicate_mask.sum())
            report.duplicates_removed = duplicates
            report.rejected_reasons["id_caso duplicado"] += duplicates

    report.rows_clean = len(clean)
    report.rows_rejected = len(rejected)

    # ------------------------------------------------------------------
    # Métricas sobre las filas que sí se publican
    # ------------------------------------------------------------------
    report.output_nulls.update(
        {str(column): int(value) for column, value in clean.isna().sum().items()}
    )

    if not clean.empty:
        ages = clean["edad"].dropna()
        if not ages.empty:
            report.age_min = int(ages.min())
            report.age_max = int(ages.max())
            report.age_sum = int(ages.sum())
            report.age_count = int(ages.count())

        for column in ("sexo", "tipo_contagio", "recuperado"):
            report.categories[column].update(count_values(clean[column]))
        report.categories["unidad_edad"].update(
            count_values(raw.loc[~rejected_mask, "_unidad_edad"])
        )

        report.departments.update(
            count_values(clean["nombre_departamento"])
        )
        report.municipalities.update(
            clean["nombre_municipio"].dropna().astype("string").value_counts().to_dict()
        )

    # ------------------------------------------------------------------
    # Inconsistencias lógicas (se reportan, no se descartan)
    # ------------------------------------------------------------------
    onset = clean["fecha_inicio_sintomas"]
    death = clean["fecha_muerte"]
    recovery = clean["fecha_recuperacion"]
    diagnosis = clean["fecha_diagnostico"]

    recovered = clean["recuperado"].fillna("")
    checks = {
        "muerte_con_estado_no_fallecido": death.notna() & (recovered != "Fallecido"),
        "fallecido_sin_fecha_de_muerte": (recovered == "Fallecido") & death.isna(),
        "muerte_antes_de_sintomas": death.notna() & onset.notna() & (death < onset),
        "recuperacion_antes_de_sintomas": recovery.notna()
        & onset.notna()
        & (recovery < onset),
        "diagnostico_antes_de_sintomas": diagnosis.notna()
        & onset.notna()
        & (diagnosis < onset),
    }
    for name, mask in checks.items():
        if mask.any():
            report.inconsistencies[name] = int(mask.sum())

    return clean, rejected, report
