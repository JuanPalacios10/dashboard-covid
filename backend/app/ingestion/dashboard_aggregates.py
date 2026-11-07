"""Preagregación de las vistas del tablero desde la capa Parquet.

La API nunca recorre ``casos_covid`` para pintar el tablero. Este módulo
reconstruye documentos pequeños y autocontenidos en MongoDB:

* KPIs nacionales acumulados y por año.
* Series nacionales y por departamento (top municipios + "Otros").
* Totales territoriales por departamento.
* Demografía por sexo y grupo etario.
* Mapa de calor departamento × mes (o × año en la vista acumulada).

Las definiciones históricas usan las fechas de evento del dataset:

* fallecido: ``fecha_muerte`` no nula y <= corte;
* recuperado: ``fecha_recuperacion`` no nula, <= corte y sin muerte <= corte;
* activo: sin ninguna de las dos fechas terminales <= corte.

Para la vista por año se usa la cohorte de casos reportados en ese año y su
estado al cierre del año. Para la vista acumulada se usa el corte real del
dataset (2024-01-17).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from pymongo import ReplaceOne
from pymongo.collection import Collection

TOP_MUNICIPIOS = 5

BASE_WINDOW_DAYS = 56
POSTERIOR_DAYS = 60
GENERATION_DAYS = 5.0
QUALITY_ALTA_DAYS = 56
QUALITY_MEDIA_DAYS = 28

AGE_LABELS: tuple[str, ...] = (
    "0-9",
    "10-19",
    "20-29",
    "30-39",
    "40-49",
    "50-59",
    "60-69",
    "70-79",
    "80+",
)
AGE_BINS = (0, 10, 20, 30, 40, 50, 60, 70, 80, 121)
SEXO_LABELS = {"F": "Femenino", "M": "Masculino", "I": "Indeterminado"}
SEXO_ORDER = ("Femenino", "Masculino", "Indeterminado", "No informado")
MONTH_LABELS = (
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
)

PARQUET_COLUMNS = (
    "fecha_reporte_web",
    "codigo_divipola_departamento",
    "nombre_departamento",
    "codigo_divipola_municipio",
    "nombre_municipio",
    "edad",
    "sexo",
    "fecha_muerte",
    "fecha_recuperacion",
)


class DashboardAggregationError(RuntimeError):
    """No fue posible construir los agregados del tablero."""


def _parquet_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("anio=*/casos.parquet"))
    if not files:
        files = sorted(directory.glob("*.parquet"))
    if not files:
        raise DashboardAggregationError(
            f"No se encontraron archivos Parquet en {directory}."
        )
    return files


def _year_from_path(path: Path) -> int | None:
    parent = path.parent.name
    if parent.startswith("anio="):
        try:
            return int(parent.split("=", 1)[1])
        except ValueError:
            return None
    return None


def _read_frame(path: Path) -> pd.DataFrame:
    frame = pq.read_table(path, columns=list(PARQUET_COLUMNS)).to_pandas()
    if frame.empty:
        return frame

    for column in ("fecha_reporte_web", "fecha_muerte", "fecha_recuperacion"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")

    frame = frame[frame["fecha_reporte_web"].notna()].copy()
    frame["fecha"] = frame["fecha_reporte_web"].dt.normalize()
    frame["codigo_departamento"] = (
        frame["codigo_divipola_departamento"].astype("string").fillna("")
    )
    frame["nombre_departamento"] = (
        frame["nombre_departamento"].astype("string").fillna("SIN NOMBRE")
    )
    frame["codigo_municipio"] = (
        frame["codigo_divipola_municipio"].astype("string").fillna("")
    )
    frame["nombre_municipio"] = (
        frame["nombre_municipio"].astype("string").fillna("SIN NOMBRE")
    )
    frame["edad"] = pd.to_numeric(frame["edad"], errors="coerce").fillna(-1).astype("int64")
    return frame


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return datetime.combine(value.date(), time.min, tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise DashboardAggregationError(f"Fecha no válida para agregados: {value!r}")


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _series_values(series: pd.Series, dates: pd.DatetimeIndex) -> list[int]:
    return [_int(value) for value in series.reindex(dates, fill_value=0).tolist()]


def _estimate_r(values: list[int]) -> float:
    """Estima R con el crecimiento del promedio móvil de 7 días."""

    if not values or sum(values) <= 0:
        return 0.0
    last_window = values[-7:]
    previous_window = values[-14:-7] if len(values) >= 14 else last_window
    last_average = sum(last_window) / len(last_window)
    previous_average = sum(previous_window) / len(previous_window)
    growth = math.log((last_average + 1.0) / (previous_average + 1.0)) / 7.0
    return round(max(0.0, min(3.0, math.exp(growth * GENERATION_DAYS))), 4)


def _max_7d_average(values: list[int]) -> float:
    if not values:
        return 0.0
    windows = [
        sum(values[index - 6 : index + 1]) / 7.0
        for index in range(6, len(values))
    ]
    return round(max(windows) if windows else sum(values) / len(values), 2)


def _quality(
    base_dates: pd.DatetimeIndex,
    base_values: list[int],
) -> dict[str, Any]:
    days = len(base_dates)
    days_with_data = sum(1 for value in base_values if value > 0)
    if sum(base_values) <= 0:
        level = "baja"
        message = "Sin casos en la ventana de proyección."
    elif days >= QUALITY_ALTA_DAYS:
        level = "alta"
        message = f"Base de {days} días."
    elif days >= QUALITY_MEDIA_DAYS:
        level = "media"
        message = f"Base parcial de {days} días."
    else:
        level = "baja"
        message = f"Solo {days} días de base; proyección indicativa."
    return {
        "nivel": level,
        "dias_base": days,
        "dias_con_datos": days_with_data,
        "mensaje": message,
    }


def _cumulative_series(
    counter: Counter[Any],
    key: str | None = None,
) -> tuple[list[pd.Timestamp], list[int]]:
    if key is None:
        items = sorted(counter.items(), key=lambda item: item[0])
    else:
        items = sorted(
            (
                (item[0][1], item[1])
                for item in counter.items()
                if item[0][0] == key
            ),
            key=lambda item: item[0],
        )
    dates: list[pd.Timestamp] = []
    cumulative: list[int] = []
    total = 0
    for value_date, count in items:
        total += _int(count)
        dates.append(pd.Timestamp(value_date))
        cumulative.append(total)
    return dates, cumulative


def _cumulative_at(
    dates: list[pd.Timestamp],
    cumulative: list[int],
    target: pd.Timestamp,
) -> int:
    index = bisect_right(dates, target) - 1
    return cumulative[index] if index >= 0 else 0


def _period_specs(
    year_payloads: list[dict[str, Any]],
    max_report_date: pd.Timestamp,
    daily_national: Counter[pd.Timestamp],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for payload in sorted(year_payloads, key=lambda item: item["year"]):
        year = int(payload["year"])
        year_dates = [value for value in daily_national if value.year == year]
        first_date = (
            min(year_dates) if year_dates else pd.Timestamp(date(year, 1, 1))
        )
        specs.append(
            {
                "key": str(year),
                "anio": year,
                "periodo": "anual",
                "cutoff": payload["cutoff"],
                "period_start": max(pd.Timestamp(date(year, 1, 1)), first_date),
            }
        )
    first_date = (
        min(daily_national) if daily_national else max_report_date
    )
    specs.append(
        {
            "key": "acumulado",
            "anio": None,
            "periodo": "acumulado",
            "cutoff": max_report_date,
            "period_start": pd.Timestamp(first_date),
        }
    )
    return specs


def _kpi_document(
    *,
    doc_id: str,
    periodo: str,
    anio: int | None,
    fecha_corte: Any,
    confirmados: int,
    fallecidos: int,
    recuperados: int,
    activos: int,
    actualizado_en: datetime,
) -> dict[str, Any]:
    return {
        "_id": doc_id,
        "scope": "nacional",
        "periodo": periodo,
        "anio": anio,
        "fecha_corte": _as_datetime(fecha_corte),
        "actualizado_en": actualizado_en,
        "casos_confirmados": confirmados,
        "fallecidos": fallecidos,
        "recuperados": recuperados,
        "activos": activos,
        "tasa_letalidad": round(fallecidos / confirmados, 6) if confirmados else 0.0,
        "tasa_recuperacion": round(recuperados / confirmados, 6) if confirmados else 0.0,
        "fuente": "casos_covid",
        "version_esquema": 2,
    }


def _series_document(
    *,
    doc_id: str,
    tipo: str,
    anio: int | None,
    periodo: str,
    granularidad: str,
    fechas: Iterable[str],
    series: list[dict[str, Any]],
    departamento: dict[str, str] | None,
    fecha_corte: Any,
    actualizado_en: datetime,
) -> dict[str, Any]:
    return {
        "_id": doc_id,
        "tipo": tipo,
        "anio": anio,
        "periodo": periodo,
        "granularidad": granularidad,
        "departamento": departamento,
        "fecha_corte": _as_datetime(fecha_corte),
        "fechas": list(fechas),
        "series": series,
        "actualizado_en": actualizado_en,
    }


def _territorios_document(
    *,
    doc_id: str,
    periodo: str,
    anio: int | None,
    fecha_corte: Any,
    departamentos: list[dict[str, Any]],
    total: int,
    actualizado_en: datetime,
) -> dict[str, Any]:
    return {
        "_id": doc_id,
        "periodo": periodo,
        "anio": anio,
        "fecha_corte": _as_datetime(fecha_corte),
        "total": total,
        "departamentos": departamentos,
        "actualizado_en": actualizado_en,
    }


def _demografia_document(
    *,
    doc_id: str,
    periodo: str,
    anio: int | None,
    fecha_corte: Any,
    sexo_counts: Counter[str],
    sexo_deaths: Counter[str],
    edad_counts: Counter[str],
    edad_deaths: Counter[str],
    total: int,
    actualizado_en: datetime,
) -> dict[str, Any]:
    sexo = []
    for nombre in SEXO_ORDER:
        count = _int(sexo_counts.get(nombre, 0))
        deaths = _int(sexo_deaths.get(nombre, 0))
        sexo.append(
            {
                "nombre": nombre,
                "total": count,
                "fallecidos": deaths,
                "porcentaje": round(count / total * 100, 4) if total else 0.0,
                "tasa_letalidad": round(deaths / count, 6) if count else 0.0,
            }
        )

    edad = []
    for grupo in AGE_LABELS:
        count = _int(edad_counts.get(grupo, 0))
        deaths = _int(edad_deaths.get(grupo, 0))
        edad.append(
            {
                "grupo": grupo,
                "total": count,
                "fallecidos": deaths,
                "porcentaje": round(count / total * 100, 4) if total else 0.0,
                "tasa_letalidad": round(deaths / count, 6) if count else 0.0,
            }
        )

    return {
        "_id": doc_id,
        "periodo": periodo,
        "anio": anio,
        "fecha_corte": _as_datetime(fecha_corte),
        "total": total,
        "sexo": sexo,
        "edad": edad,
        "actualizado_en": actualizado_en,
    }


def _heatmap_document(
    *,
    doc_id: str,
    periodo: str,
    anio: int | None,
    fecha_corte: Any,
    columnas: list[str],
    filas: list[dict[str, Any]],
    actualizado_en: datetime,
) -> dict[str, Any]:
    return {
        "_id": doc_id,
        "periodo": periodo,
        "anio": anio,
        "fecha_corte": _as_datetime(fecha_corte),
        "columnas": columnas,
        "filas": filas,
        "actualizado_en": actualizado_en,
    }


def _replace_documents(
    collection: Collection[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> None:
    if not documents:
        return
    new_ids = {document["_id"] for document in documents}
    existing_ids = set(collection.distinct("_id"))
    stale_ids = existing_ids - new_ids
    if stale_ids:
        collection.delete_many({"_id": {"$in": list(stale_ids)}})
    collection.bulk_write(
        [
            ReplaceOne({"_id": document["_id"]}, document, upsert=True)
            for document in documents
        ],
        ordered=False,
    )


def _build_year_series(
    *,
    year: int,
    dates: pd.DatetimeIndex,
    dept_daily: pd.Series,
    mun_daily: pd.Series,
    dept_totals: pd.Series,
    dept_names: dict[str, str],
    mun_names: dict[tuple[str, str], str],
    cutoff: Any,
    actualizado_en: datetime,
    top_municipios: int,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []

    for dept_code in dept_totals.index:
        dept_code = str(dept_code)
        dept_series = dept_daily.loc[dept_code]
        if isinstance(dept_series, pd.DataFrame):
            dept_series = dept_series.sum(axis=0)
        dept_series = dept_series.reindex(dates, fill_value=0)

        mun_sub = mun_daily.loc[dept_code]
        if isinstance(mun_sub, pd.DataFrame):
            mun_sub = mun_sub.squeeze(axis=0)
        mun_totals = mun_sub.groupby(level=0).sum().sort_values(ascending=False)

        series: list[dict[str, Any]] = []
        top_sum = pd.Series(0, index=dates, dtype="int64")
        for mun_code, total in mun_totals.head(top_municipios).items():
            mun_code = str(mun_code)
            values = mun_sub.loc[mun_code].reindex(dates, fill_value=0)
            if isinstance(values, pd.DataFrame):
                values = values.sum(axis=0)
            values = values.astype("int64")
            top_sum = top_sum.add(values, fill_value=0)
            series.append(
                {
                    "codigo": mun_code,
                    "nombre": mun_names.get((dept_code, mun_code), mun_code),
                    "total": _int(total),
                    "valores": _series_values(values, dates),
                }
            )

        others = dept_series.astype("int64").subtract(top_sum, fill_value=0)
        if _int(others.sum()) > 0:
            series.append(
                {
                    "codigo": "otros",
                    "nombre": "Otros",
                    "total": _int(others.sum()),
                    "valores": _series_values(others, dates),
                }
            )

        documents.append(
            _series_document(
                doc_id=f"series:departamento:{dept_code}:{year}",
                tipo="departamento",
                anio=year,
                periodo="anual",
                granularidad="diaria",
                fechas=(value.strftime("%Y-%m-%d") for value in dates),
                series=series,
                departamento={
                    "codigo": dept_code,
                    "nombre": dept_names.get(dept_code, dept_code),
                },
                fecha_corte=cutoff,
                actualizado_en=actualizado_en,
            )
        )

    return documents


def consolidate_dashboard_from_parquet(
    parquet_dir: Path,
    dashboard_collection: Collection[dict[str, Any]],
    kpis_collection: Collection[dict[str, Any]],
    *,
    top_municipios: int = TOP_MUNICIPIOS,
) -> dict[str, Any]:
    """Reconstruye todos los agregados del tablero desde Parquet.

    La escritura se hace al final, cuando todos los documentos fueron
    calculados. Si algo falla antes, la API sigue viendo la versión anterior.
    """

    files = _parquet_files(parquet_dir)
    actualizado_en = datetime.now(UTC)

    all_dept_names: dict[str, str] = {}
    all_mun_names: dict[tuple[str, str], str] = {}
    dept_totals_all: Counter[str] = Counter()
    dept_deaths_all: Counter[str] = Counter()
    mun_totals_all: Counter[tuple[str, str]] = Counter()
    monthly_national: Counter[str] = Counter()
    monthly_dept: Counter[tuple[str, str]] = Counter()
    monthly_mun: Counter[tuple[str, str, str]] = Counter()
    daily_national: Counter[pd.Timestamp] = Counter()
    daily_dept: Counter[tuple[str, pd.Timestamp]] = Counter()
    end_active_national: Counter[pd.Timestamp] = Counter()
    end_active_dept: Counter[tuple[str, pd.Timestamp]] = Counter()
    sexo_counts_all: Counter[str] = Counter()
    sexo_deaths_all: Counter[str] = Counter()
    edad_counts_all: Counter[str] = Counter()
    edad_deaths_all: Counter[str] = Counter()
    heatmap_years: defaultdict[str, Counter[int]] = defaultdict(Counter)

    cumulative_confirmed = 0
    cumulative_deaths = 0
    cumulative_recovered = 0
    cumulative_active = 0
    max_report_date: pd.Timestamp | None = None

    kpi_documents: list[dict[str, Any]] = []
    dashboard_documents: list[dict[str, Any]] = []
    year_payloads: list[dict[str, Any]] = []

    for path in files:
        year = _year_from_path(path)
        frame = _read_frame(path)
        if frame.empty:
            continue
        if year is None:
            year = _int(frame["fecha"].dt.year.mode().iloc[0])

        dept_names = (
            frame.groupby("codigo_departamento")["nombre_departamento"]
            .first()
            .to_dict()
        )
        mun_names = (
            frame.groupby(["codigo_departamento", "codigo_municipio"])[
                "nombre_municipio"
            ]
            .first()
            .to_dict()
        )
        all_dept_names.update({str(k): str(v) for k, v in dept_names.items()})
        all_mun_names.update(
            {(str(k[0]), str(k[1])): str(v) for k, v in mun_names.items()}
        )

        death_all = frame["fecha_muerte"].notna()
        recovery_all = frame["fecha_recuperacion"].notna() & ~death_all
        active_all = ~death_all & ~recovery_all

        cumulative_confirmed += len(frame)
        cumulative_deaths += _int(death_all.sum())
        cumulative_recovered += _int(recovery_all.sum())
        cumulative_active += _int(active_all.sum())

        frame_max_date = frame["fecha"].max()
        if max_report_date is None or frame_max_date > max_report_date:
            max_report_date = frame_max_date

        cutoff = (
            frame_max_date
            if year >= 2024
            else pd.Timestamp(date(year, 12, 31))
        )
        death = frame["fecha_muerte"].notna() & (
            frame["fecha_muerte"] <= cutoff
        )
        recovery = (
            frame["fecha_recuperacion"].notna()
            & (frame["fecha_recuperacion"] <= cutoff)
            & ~death
        )
        active = ~death & ~recovery

        kpi_documents.append(
            _kpi_document(
                doc_id=str(year),
                periodo="anual",
                anio=year,
                fecha_corte=cutoff,
                confirmados=len(frame),
                fallecidos=_int(death.sum()),
                recuperados=_int(recovery.sum()),
                activos=_int(active.sum()),
                actualizado_en=actualizado_en,
            )
        )

        dates = pd.date_range(frame["fecha"].min(), frame_max_date, freq="D")
        national_daily = frame.groupby("fecha").size()
        daily_national.update(
            {pd.Timestamp(key): _int(value) for key, value in national_daily.to_dict().items()}
        )
        dashboard_documents.append(
            _series_document(
                doc_id=f"series:nacional:{year}",
                tipo="nacional",
                anio=year,
                periodo="anual",
                granularidad="diaria",
                fechas=(value.strftime("%Y-%m-%d") for value in dates),
                series=[
                    {
                        "codigo": "00",
                        "nombre": "Nacional",
                        "total": len(frame),
                        "valores": _series_values(national_daily, dates),
                    }
                ],
                departamento=None,
                fecha_corte=cutoff,
                actualizado_en=actualizado_en,
            )
        )

        dept_daily = frame.groupby(["codigo_departamento", "fecha"]).size()
        mun_daily = frame.groupby(
            ["codigo_departamento", "codigo_municipio", "fecha"]
        ).size()
        dept_totals = frame.groupby("codigo_departamento").size()
        dept_deaths = frame[death].groupby("codigo_departamento").size()

        daily_dept.update(
            {
                (str(key[0]), pd.Timestamp(key[1])): _int(value)
                for key, value in dept_daily.to_dict().items()
            }
        )
        end_active = frame[["fecha_muerte", "fecha_recuperacion"]].min(axis=1)
        has_end = end_active.notna()
        end_active = end_active[has_end].dt.normalize()
        end_active = end_active.where(
            end_active >= frame.loc[has_end, "fecha"],
            frame.loc[has_end, "fecha"],
        )
        end_active_national.update(end_active.value_counts().to_dict())
        end_active_frame = frame.loc[
            end_active.index, ["codigo_departamento"]
        ].copy()
        end_active_frame["end_active"] = end_active
        end_active_dept.update(
            {
                (str(key[0]), pd.Timestamp(key[1])): _int(value)
                for key, value in end_active_frame.groupby(
                    ["codigo_departamento", "end_active"]
                ).size().to_dict().items()
            }
        )

        dashboard_documents.extend(
            _build_year_series(
                year=year,
                dates=dates,
                dept_daily=dept_daily,
                mun_daily=mun_daily,
                dept_totals=dept_totals,
                dept_names={str(k): str(v) for k, v in dept_names.items()},
                mun_names={
                    (str(k[0]), str(k[1])): str(v)
                    for k, v in mun_names.items()
                },
                cutoff=cutoff,
                actualizado_en=actualizado_en,
                top_municipios=top_municipios,
            )
        )

        dept_totals_all.update(
            {str(k): _int(v) for k, v in dept_totals.to_dict().items()}
        )
        dept_deaths_all.update(
            {str(k): _int(v) for k, v in dept_deaths.to_dict().items()}
        )
        mun_totals_all.update(
            {
                (str(k[0]), str(k[1])): _int(v)
                for k, v in mun_daily.groupby(level=[0, 1]).sum().to_dict().items()
            }
        )

        month = frame["fecha"].dt.to_period("M").astype(str)
        monthly_national.update(
            {str(k): _int(v) for k, v in frame.groupby(month).size().to_dict().items()}
        )
        monthly_dept.update(
            {
                (str(k[0]), str(k[1])): _int(v)
                for k, v in frame.groupby(
                    ["codigo_departamento", month]
                ).size().to_dict().items()
            }
        )
        monthly_mun.update(
            {
                (str(k[0]), str(k[1]), str(k[2])): _int(v)
                for k, v in frame.groupby(
                    ["codigo_departamento", "codigo_municipio", month]
                ).size().to_dict().items()
            }
        )

        sexo = frame["sexo"].map(SEXO_LABELS).fillna("No informado")
        edad = (
            pd.cut(
                frame["edad"],
                bins=AGE_BINS,
                labels=AGE_LABELS,
                right=False,
                include_lowest=True,
            )
            .astype("string")
            .fillna("No informado")
        )
        sexo_counts = Counter(
            {str(k): _int(v) for k, v in sexo.value_counts().to_dict().items()}
        )
        sexo_deaths = Counter(
            {
                str(k): _int(v)
                for k, v in death.groupby(sexo).sum().to_dict().items()
            }
        )
        edad_counts = Counter(
            {str(k): _int(v) for k, v in edad.value_counts().to_dict().items()}
        )
        edad_deaths = Counter(
            {
                str(k): _int(v)
                for k, v in death.groupby(edad).sum().to_dict().items()
            }
        )

        sexo_counts_all.update(
            {
                str(k): _int(v)
                for k, v in sexo.value_counts().to_dict().items()
            }
        )
        sexo_deaths_all.update(
            {
                str(k): _int(v)
                for k, v in death_all.groupby(sexo).sum().to_dict().items()
            }
        )
        edad_counts_all.update(
            {
                str(k): _int(v)
                for k, v in edad.value_counts().to_dict().items()
            }
        )
        edad_deaths_all.update(
            {
                str(k): _int(v)
                for k, v in death_all.groupby(edad).sum().to_dict().items()
            }
        )

        dashboard_documents.append(
            _demografia_document(
                doc_id=f"demografia:{year}",
                periodo="anual",
                anio=year,
                fecha_corte=cutoff,
                sexo_counts=sexo_counts,
                sexo_deaths=sexo_deaths,
                edad_counts=edad_counts,
                edad_deaths=edad_deaths,
                total=len(frame),
                actualizado_en=actualizado_en,
            )
        )

        year_heatmap = {
            (str(k[0]), int(k[1])): _int(v)
            for k, v in frame.groupby(
                ["codigo_departamento", frame["fecha"].dt.month]
            ).size().to_dict().items()
        }
        for (dept_code, month_number), count in year_heatmap.items():
            heatmap_years[dept_code][year] += count

        year_payloads.append(
            {
                "year": year,
                "cutoff": cutoff,
                "confirmed": len(frame),
                "dept_totals": {
                    str(k): _int(v) for k, v in dept_totals.to_dict().items()
                },
                "dept_deaths": {
                    str(k): _int(v) for k, v in dept_deaths.to_dict().items()
                },
                "heatmap": year_heatmap,
                "dates": [value.strftime("%Y-%m-%d") for value in dates],
            }
        )

        del frame, dept_daily, mun_daily, dept_totals, dept_deaths
        del sexo, edad, sexo_counts, sexo_deaths, edad_counts, edad_deaths
        del year_heatmap

    if max_report_date is None or not year_payloads:
        raise DashboardAggregationError(
            "No se encontraron casos válidos para construir el tablero."
        )

    kpi_documents.append(
        _kpi_document(
            doc_id="nacional",
            periodo="acumulado",
            anio=None,
            fecha_corte=max_report_date,
            confirmados=cumulative_confirmed,
            fallecidos=cumulative_deaths,
            recuperados=cumulative_recovered,
            activos=cumulative_active,
            actualizado_en=actualizado_en,
        )
    )

    months = [str(value) for value in pd.period_range(
        pd.Period(min(monthly_national), freq="M"),
        pd.Period(max(monthly_national), freq="M"),
        freq="M",
    )]
    national_monthly_values = [
        _int(monthly_national.get(month, 0)) for month in months
    ]
    dashboard_documents.append(
        _series_document(
            doc_id="series:nacional:acumulado",
            tipo="nacional",
            anio=None,
            periodo="acumulado",
            granularidad="mensual",
            fechas=months,
            series=[
                {
                    "codigo": "00",
                    "nombre": "Nacional",
                    "total": sum(national_monthly_values),
                    "valores": national_monthly_values,
                }
            ],
            departamento=None,
            fecha_corte=max_report_date,
            actualizado_en=actualizado_en,
        )
    )

    for dept_code, dept_name in sorted(all_dept_names.items()):
        dept_values = [
            _int(monthly_dept.get((dept_code, month), 0)) for month in months
        ]
        mun_totals = {
            mun_code: total
            for (code, mun_code), total in mun_totals_all.items()
            if code == dept_code
        }
        top = sorted(
            mun_totals.items(), key=lambda item: item[1], reverse=True
        )[:top_municipios]

        series: list[dict[str, Any]] = []
        top_sum = [0] * len(months)
        for mun_code, total in top:
            values = [
                _int(monthly_mun.get((dept_code, mun_code, month), 0))
                for month in months
            ]
            top_sum = [left + right for left, right in zip(top_sum, values)]
            series.append(
                {
                    "codigo": mun_code,
                    "nombre": all_mun_names.get(
                        (dept_code, mun_code), mun_code
                    ),
                    "total": _int(total),
                    "valores": values,
                }
            )

        others = [
            dept_value - top_value
            for dept_value, top_value in zip(dept_values, top_sum)
        ]
        if sum(others) > 0:
            series.append(
                {
                    "codigo": "otros",
                    "nombre": "Otros",
                    "total": sum(others),
                    "valores": others,
                }
            )

        dashboard_documents.append(
            _series_document(
                doc_id=f"series:departamento:{dept_code}:acumulado",
                tipo="departamento",
                anio=None,
                periodo="acumulado",
                granularidad="mensual",
                fechas=months,
                series=series,
                departamento={"codigo": dept_code, "nombre": dept_name},
                fecha_corte=max_report_date,
                actualizado_en=actualizado_en,
            )
        )

    # Completa la serie de cada departamento para todos los años, incluso
    # cuando no tuvo casos. Así el filtro territorial nunca devuelve 404 por
    # un departamento que existe pero cuyo año quedó en cero.
    existing_series_ids = {
        document["_id"]
        for document in dashboard_documents
        if document["_id"].startswith("series:departamento:")
    }
    for payload in year_payloads:
        for code, name in sorted(all_dept_names.items()):
            doc_id = f"series:departamento:{code}:{payload['year']}"
            if doc_id in existing_series_ids:
                continue
            dashboard_documents.append(
                _series_document(
                    doc_id=doc_id,
                    tipo="departamento",
                    anio=payload["year"],
                    periodo="anual",
                    granularidad="diaria",
                    fechas=payload["dates"],
                    series=[
                        {
                            "codigo": code,
                            "nombre": "Sin casos",
                            "total": 0,
                            "valores": [0] * len(payload["dates"]),
                        }
                    ],
                    departamento={"codigo": code, "nombre": name},
                    fecha_corte=payload["cutoff"],
                    actualizado_en=actualizado_en,
                )
            )
            existing_series_ids.add(doc_id)

    for payload in year_payloads:
        departments = []
        for code, name in all_dept_names.items():
            total = _int(payload["dept_totals"].get(code, 0))
            deaths = _int(payload["dept_deaths"].get(code, 0))
            departments.append(
                {
                    "codigo": code,
                    "nombre": name,
                    "total": total,
                    "fallecidos": deaths,
                    "tasa_letalidad": round(deaths / total, 6) if total else 0.0,
                    "participacion": (
                        round(total / payload["confirmed"] * 100, 4)
                        if payload["confirmed"]
                        else 0.0
                    ),
                }
            )
        departments.sort(key=lambda item: (-item["total"], item["nombre"]))
        dashboard_documents.append(
            _territorios_document(
                doc_id=f"territorios:{payload['year']}",
                periodo="anual",
                anio=payload["year"],
                fecha_corte=payload["cutoff"],
                departamentos=departments,
                total=payload["confirmed"],
                actualizado_en=actualizado_en,
            )
        )

    departments = []
    for code, name in all_dept_names.items():
        total = _int(dept_totals_all.get(code, 0))
        deaths = _int(dept_deaths_all.get(code, 0))
        departments.append(
            {
                "codigo": code,
                "nombre": name,
                "total": total,
                "fallecidos": deaths,
                "tasa_letalidad": round(deaths / total, 6) if total else 0.0,
                "participacion": (
                    round(total / cumulative_confirmed * 100, 4)
                    if cumulative_confirmed
                    else 0.0
                ),
            }
        )
    departments.sort(key=lambda item: (-item["total"], item["nombre"]))
    dashboard_documents.append(
        _territorios_document(
            doc_id="territorios:acumulado",
            periodo="acumulado",
            anio=None,
            fecha_corte=max_report_date,
            departamentos=departments,
            total=cumulative_confirmed,
            actualizado_en=actualizado_en,
        )
    )

    dashboard_documents.append(
        _demografia_document(
            doc_id="demografia:acumulado",
            periodo="acumulado",
            anio=None,
            fecha_corte=max_report_date,
            sexo_counts=sexo_counts_all,
            sexo_deaths=sexo_deaths_all,
            edad_counts=edad_counts_all,
            edad_deaths=edad_deaths_all,
            total=cumulative_confirmed,
            actualizado_en=actualizado_en,
        )
    )

    for payload in year_payloads:
        rows = []
        for code, name in all_dept_names.items():
            values = [0] * 12
            for (dept_code, month_number), count in payload["heatmap"].items():
                if dept_code == code:
                    values[month_number - 1] = count
            rows.append(
                {
                    "codigo": code,
                    "nombre": name,
                    "total": sum(values),
                    "valores": values,
                }
            )
        rows.sort(key=lambda item: (-item["total"], item["nombre"]))
        dashboard_documents.append(
            _heatmap_document(
                doc_id=f"heatmap:{payload['year']}",
                periodo="anual",
                anio=payload["year"],
                fecha_corte=payload["cutoff"],
                columnas=list(MONTH_LABELS),
                filas=rows,
                actualizado_en=actualizado_en,
            )
        )

    years = sorted(payload["year"] for payload in year_payloads)
    rows = []
    for code, name in all_dept_names.items():
        values = [_int(heatmap_years[code].get(year, 0)) for year in years]
        rows.append(
            {
                "codigo": code,
                "nombre": name,
                "total": sum(values),
                "valores": values,
            }
        )
    rows.sort(key=lambda item: (-item["total"], item["nombre"]))
    dashboard_documents.append(
        _heatmap_document(
            doc_id="heatmap:acumulado",
            periodo="acumulado",
            anio=None,
            fecha_corte=max_report_date,
            columnas=[str(year) for year in years],
            filas=rows,
            actualizado_en=actualizado_en,
        )
    )

    # Bases precalculadas para la pestaña de proyecciones. La API solo
    # ejecutará el modelo sobre estas series; no consultará casos_covid.
    national_report_dates, national_report_cum = _cumulative_series(
        daily_national
    )
    national_end_dates, national_end_cum = _cumulative_series(
        end_active_national
    )
    dept_report_cum = {
        code: _cumulative_series(daily_dept, code)
        for code in all_dept_names
    }
    dept_end_cum = {
        code: _cumulative_series(end_active_dept, code)
        for code in all_dept_names
    }

    territories: list[dict[str, Any]] = [
        {
            "code": None,
            "name": "Nacional",
            "tipo": "nacional",
            "report_dates": national_report_dates,
            "report_cum": national_report_cum,
            "end_dates": national_end_dates,
            "end_cum": national_end_cum,
        }
    ]
    for code, name in sorted(all_dept_names.items()):
        report_dates, report_cum = dept_report_cum[code]
        end_dates, end_cum = dept_end_cum[code]
        territories.append(
            {
                "code": code,
                "name": name,
                "tipo": "departamento",
                "report_dates": report_dates,
                "report_cum": report_cum,
                "end_dates": end_dates,
                "end_cum": end_cum,
            }
        )

    for spec in _period_specs(year_payloads, max_report_date, daily_national):
        cutoff = pd.Timestamp(spec["cutoff"])
        base_start = max(
            pd.Timestamp(spec["period_start"]),
            cutoff - pd.Timedelta(days=BASE_WINDOW_DAYS - 1),
        )
        base_dates = pd.date_range(base_start, cutoff, freq="D")
        posterior_dates: list[pd.Timestamp] = []
        if spec["anio"] is not None and spec["anio"] < 2024:
            posterior_start = cutoff + pd.Timedelta(days=1)
            posterior_end = min(
                cutoff + pd.Timedelta(days=POSTERIOR_DAYS),
                max_report_date,
            )
            if posterior_start <= posterior_end:
                posterior_dates = list(
                    pd.date_range(posterior_start, posterior_end, freq="D")
                )

        for territory in territories:
            code = territory["code"]
            if code is None:
                base_values = [
                    _int(daily_national.get(day, 0)) for day in base_dates
                ]
                posterior_values = [
                    _int(daily_national.get(day, 0))
                    for day in posterior_dates
                ]
            else:
                base_values = [
                    _int(daily_dept.get((code, day), 0))
                    for day in base_dates
                ]
                posterior_values = [
                    _int(daily_dept.get((code, day), 0))
                    for day in posterior_dates
                ]

            period_dates = pd.date_range(
                pd.Timestamp(spec["period_start"]),
                cutoff,
                freq="D",
            )
            if code is None:
                period_values = [
                    _int(daily_national.get(day, 0)) for day in period_dates
                ]
            else:
                period_values = [
                    _int(daily_dept.get((code, day), 0))
                    for day in period_dates
                ]
            max_7d_period = _max_7d_average(period_values)

            active_series = [
                _cumulative_at(
                    territory["report_dates"],
                    territory["report_cum"],
                    day,
                )
                - _cumulative_at(
                    territory["end_dates"],
                    territory["end_cum"],
                    day,
                )
                for day in base_dates
            ]
            active_at_cutoff = _cumulative_at(
                territory["report_dates"],
                territory["report_cum"],
                cutoff,
            ) - _cumulative_at(
                territory["end_dates"],
                territory["end_cum"],
                cutoff,
            )
            last_window = base_values[-7:]
            promedio_7d_actual = (
                sum(last_window) / len(last_window) if last_window else 0.0
            )
            r_estimado = _estimate_r(base_values)
            calidad = _quality(base_dates, base_values)

            if code is None:
                doc_id = f"proyeccion:nacional:{spec['key']}"
                departamento = None
            else:
                doc_id = f"proyeccion:departamento:{code}:{spec['key']}"
                departamento = {
                    "codigo": code,
                    "nombre": territory["name"],
                }

            dashboard_documents.append(
                {
                    "_id": doc_id,
                    "tipo": territory["tipo"],
                    "periodo": spec["periodo"],
                    "anio": spec["anio"],
                    "fecha_corte": _as_datetime(cutoff),
                    "departamento": departamento,
                    "calidad": calidad,
                    "base": {
                        "fechas": [
                            value.strftime("%Y-%m-%d")
                            for value in base_dates
                        ],
                        "casos_diarios": base_values,
                        "activos_diarios": [
                            max(0, _int(value)) for value in active_series
                        ],
                        "activos_al_corte": max(0, _int(active_at_cutoff)),
                        "promedio_7d_actual": round(promedio_7d_actual, 2),
                        "max_7d_periodo": max_7d_period,
                        "r_estimado": r_estimado,
                    },
                    "observado_posterior": (
                        {
                            "fechas": [
                                value.strftime("%Y-%m-%d")
                                for value in posterior_dates
                            ],
                            "casos_diarios": posterior_values,
                        }
                        if posterior_dates
                        else None
                    ),
                    "actualizado_en": actualizado_en,
                }
            )

    _replace_documents(kpis_collection, kpi_documents)
    _replace_documents(dashboard_collection, dashboard_documents)

    return {
        "fecha_corte": max_report_date.date().isoformat(),
        "anios": years,
        "kpis": len(kpi_documents),
        "series": sum(
            1
            for document in dashboard_documents
            if document["_id"].startswith("series:")
        ),
        "territorios": sum(
            1
            for document in dashboard_documents
            if document["_id"].startswith("territorios:")
        ),
        "demografia": sum(
            1
            for document in dashboard_documents
            if document["_id"].startswith("demografia:")
        ),
        "heatmap": sum(
            1
            for document in dashboard_documents
            if document["_id"].startswith("heatmap:")
        ),
        "proyecciones": sum(
            1
            for document in dashboard_documents
            if document["_id"].startswith("proyeccion:")
        ),
        "confirmados": cumulative_confirmed,
        "fallecidos": cumulative_deaths,
        "recuperados": cumulative_recovered,
        "activos": cumulative_active,
    }
