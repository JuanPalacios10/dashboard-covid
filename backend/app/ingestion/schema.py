"""Esquema canónico del dataset de casos positivos de COVID-19.

Concentra en un único lugar:

* las columnas finales que se publican en la capa procesada,
* el mapeo entre los encabezados originales y los nombres normalizados,
* los tipos de datos esperados,
* el catálogo DANE de departamentos usado para validar/corregir códigos.
"""

from __future__ import annotations

import re
import unicodedata

import pyarrow as pa

# ---------------------------------------------------------------------------
# Columnas
# ---------------------------------------------------------------------------

# Columnas que se conservan en la salida final (nombres normalizados a
# snake_case, sin tildes ni espacios).
FINAL_COLUMNS: tuple[str, ...] = (
    "fecha_reporte_web",
    "id_caso",
    "fecha_notificacion",
    "codigo_divipola_departamento",
    "nombre_departamento",
    "codigo_divipola_municipio",
    "nombre_municipio",
    "edad",
    "sexo",
    "tipo_contagio",
    "recuperado",
    "fecha_inicio_sintomas",
    "fecha_muerte",
    "fecha_diagnostico",
    "fecha_recuperacion",
)

# Mapeo: encabezado original -> nombre final normalizado.
SOURCE_TO_FINAL: dict[str, str] = {
    "fecha reporte web": "fecha_reporte_web",
    "ID de caso": "id_caso",
    "Fecha de notificación": "fecha_notificacion",
    "Código DIVIPOLA departamento": "codigo_divipola_departamento",
    "Nombre departamento": "nombre_departamento",
    "Código DIVIPOLA municipio": "codigo_divipola_municipio",
    "Nombre municipio": "nombre_municipio",
    "Edad": "edad",
    "Unidad de medida de edad": "_unidad_edad",
    "Sexo": "sexo",
    "Tipo de contagio": "tipo_contagio",
    "Recuperado": "recuperado",
    "Fecha de inicio de síntomas": "fecha_inicio_sintomas",
    "Fecha de muerte": "fecha_muerte",
    "Fecha de diagnóstico": "fecha_diagnostico",
    "Fecha de recuperación": "fecha_recuperacion",
}

DATE_COLUMNS: tuple[str, ...] = (
    "fecha_reporte_web",
    "fecha_notificacion",
    "fecha_inicio_sintomas",
    "fecha_muerte",
    "fecha_diagnostico",
    "fecha_recuperacion",
)

# Columnas estrictamente necesarias para poder procesar una fila.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "fecha_reporte_web",
    "id_caso",
    "fecha_notificacion",
    "codigo_divipola_departamento",
    "nombre_departamento",
    "codigo_divipola_municipio",
    "nombre_municipio",
    "edad",
    "_unidad_edad",
    "sexo",
    "tipo_contagio",
    "recuperado",
    "fecha_inicio_sintomas",
    "fecha_muerte",
    "fecha_diagnostico",
    "fecha_recuperacion",
)

# ---------------------------------------------------------------------------
# Tipos de salida
# ---------------------------------------------------------------------------

FINAL_ARROW_SCHEMA = pa.schema(
    [
        pa.field("fecha_reporte_web", pa.date32()),
        pa.field("id_caso", pa.int64()),
        pa.field("fecha_notificacion", pa.date32()),
        pa.field("codigo_divipola_departamento", pa.string()),
        pa.field("nombre_departamento", pa.string()),
        pa.field("codigo_divipola_municipio", pa.string()),
        pa.field("nombre_municipio", pa.string()),
        pa.field("edad", pa.int16()),
        pa.field("sexo", pa.string()),
        pa.field("tipo_contagio", pa.string()),
        pa.field("recuperado", pa.string()),
        pa.field("fecha_inicio_sintomas", pa.date32()),
        pa.field("fecha_muerte", pa.date32()),
        pa.field("fecha_diagnostico", pa.date32()),
        pa.field("fecha_recuperacion", pa.date32()),
    ]
)

REJECTED_ARROW_SCHEMA = pa.schema(
    list(FINAL_ARROW_SCHEMA)
    + [
        pa.field("motivo_rechazo", pa.string()),
        pa.field("anio_reporte", pa.int16()),
    ]
)

# ---------------------------------------------------------------------------
# Catálogo DANE de departamentos
# ---------------------------------------------------------------------------

# Los códigos oficiales son de 2 dígitos. El dataset original pierde los ceros
# a la izquierda y, en algunos registros, ubica el código del municipio en la
# columna del departamento (p. ej. "8.001" para Barranquilla).
DEPARTAMENTOS_DANE: dict[str, str] = {
    "05": "ANTIOQUIA",
    "08": "ATLÁNTICO",
    "11": "BOGOTÁ D.C.",
    "13": "BOLÍVAR",
    "15": "BOYACÁ",
    "17": "CALDAS",
    "18": "CAQUETÁ",
    "19": "CAUCA",
    "20": "CESAR",
    "23": "CÓRDOBA",
    "25": "CUNDINAMARCA",
    "27": "CHOCÓ",
    "41": "HUILA",
    "44": "LA GUAJIRA",
    "47": "MAGDALENA",
    "50": "META",
    "52": "NARIÑO",
    "54": "NORTE DE SANTANDER",
    "63": "QUINDÍO",
    "66": "RISARALDA",
    "68": "SANTANDER",
    "70": "SUCRE",
    "73": "TOLIMA",
    "76": "VALLE DEL CAUCA",
    "81": "ARAUCA",
    "85": "CASANARE",
    "86": "PUTUMAYO",
    "88": "SAN ANDRÉS Y PROVIDENCIA",
    "91": "AMAZONAS",
    "94": "GUAINÍA",
    "95": "GUAVIARE",
    "97": "VAUPÉS",
    "99": "VICHADA",
}

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_header(name: str) -> str:
    """Normaliza un encabezado para compararlo sin depender de tildes/espacios.

    Ejemplos: ``"Código DIVIPOLA departamento"`` -> ``"codigo_divipola_departamento"``.
    """

    decomposed = unicodedata.normalize("NFKD", str(name))
    ascii_name = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_ALNUM.sub("_", ascii_name.strip().lower()).strip("_")


NORMALIZED_SOURCE_TO_FINAL: dict[str, str] = {
    normalize_header(source): final for source, final in SOURCE_TO_FINAL.items()
}

# Categorías normalizadas (la clave es el valor en mayúsculas sin espacios
# sobrantes; el valor es la etiqueta final).
SEXO_LABELS: dict[str, str] = {
    "M": "M",
    "MASCULINO": "M",
    "F": "F",
    "FEMENINO": "F",
    "I": "I",
    "INDETERMINADO": "I",
}

TIPO_CONTAGIO_LABELS: dict[str, str] = {
    "COMUNITARIA": "Comunitaria",
    "RELACIONADO": "Relacionado",
    "IMPORTADO": "Importado",
}

RECUPERADO_LABELS: dict[str, str] = {
    "RECUPERADO": "Recuperado",
    "FALLECIDO": "Fallecido",
    "ACTIVO": "Activo",
}

# Límites de calidad usados para rechazar edades imposibles.
EDAD_MINIMA = 0
EDAD_MAXIMA = 120
