# Dashboard COVID-19 Colombia

Backend para procesar y analizar los casos positivos de COVID-19 en Colombia.
La **fase 1** implementa la limpieza y normalización del dataset con Pandas y
una ingesta por chunks que no satura la memoria del servidor.

## Estado

- ✅ Ingesta por bloques de 100.000 filas (configurable).
- ✅ Normalización de encabezados a `snake_case` y selección de 15 columnas.
- ✅ Limpieza de fechas, códigos DIVIPOLA, edad, sexo y categorías.
- ✅ Deduplicación global por `id_caso` con memoria acotada.
- ✅ Salida Parquet particionada por año + manifiesto de calidad en JSON.
- ✅ API FastAPI para lanzar y consultar la ingesta.
- ✅ 18 pruebas automatizadas.
- ⏳ Persistencia en base de datos y endpoints del dashboard (fase 2).

## Estructura

```
dashboard-covid/
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # Endpoints de ingesta
│   │   ├── ingestion/
│   │   │   ├── schema.py          # Columnas, tipos y catálogo DANE
│   │   │   ├── cleaner.py         # Normalización y validación por chunk
│   │   │   ├── dedupe.py          # Deduplicación de id_caso
│   │   │   ├── writer.py          # Parquet particionado incremental
│   │   │   ├── memory.py          # Monitor de RAM
│   │   │   ├── stats.py           # Métricas de calidad
│   │   │   ├── report.py          # Manifiesto JSON
│   │   │   └── pipeline.py        # Orquestador
│   │   ├── services/jobs.py       # Job en segundo plano de la API
│   │   ├── config.py              # Configuración por variables de entorno
│   │   ├── database.py            # Reservado para la fase 2
│   │   └── main.py                # Aplicación FastAPI
│   ├── scripts/ingest_dataset.py  # CLI de ingesta
│   ├── tests/
│   ├── docs/
│   │   ├── diccionario_datos.md
│   │   └── arquitectura_ingesta.md
│   ├── data/                      # Dataset local (no versionado)
│   ├── requirements.txt
│   └── requirements-dev.txt
└── README.md
```

## Requisitos

- Python 3.11 o superior (probado con 3.14).
- ~1 GB de RAM disponible para el proceso (con `chunk_size=100.000`).
- El archivo local `Casos_positivos_de_COVID-19_Colombia.csv` (~1,4 GB).
- La ingesta acepta CSV o JSON Lines (`.json`, `.jsonl`, `.ndjson`).

## Instalación

```bash
cd /home/nicolasr/Proyectos/dashboard-covid

python -m venv .venv
source .venv/bin/activate

pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt   # solo para pruebas
```

Coloque el dataset en `backend/data/Casos_positivos_de_COVID-19_Colombia.csv`
o configure otra ruta:

```bash
cp backend/.env.example backend/.env
# edite COVID_DATASET_PATH si es necesario
```

Todas las variables usan el prefijo `COVID_`: `COVID_DATASET_PATH`,
`COVID_PROCESSED_DIR`, `COVID_CHUNK_SIZE`, `COVID_MEMORY_LIMIT_MB`,
`COVID_DEDUPLICATE`, `COVID_PARQUET_COMPRESSION`.

## Ejecutar la ingesta

```bash
cd backend

# Ingesta completa; exige --overwrite si ya existe data/processed/casos
python scripts/ingest_dataset.py --overwrite

# Prueba rápida con 20.000 filas
python scripts/ingest_dataset.py --limit-rows 20000 --overwrite

# Ajustar memoria y tamaño de bloque
python scripts/ingest_dataset.py --chunk-size 50000 --memory-limit-mb 512 --overwrite
```

Opciones principales:

| Opción | Descripción |
|---|---|
| `--source` | Ruta del CSV (por defecto `COVID_DATASET_PATH`). |
| `--output-dir` | Directorio de salida (por defecto `backend/data/processed`). |
| `--chunk-size` | Filas por bloque (por defecto 100.000). |
| `--memory-limit-mb` | Umbral máximo de RAM (por defecto 1.024 MB). |
| `--limit-rows` | Procesa solo N filas (pruebas). |
| `--overwrite` | Reemplaza la capa procesada existente. |
| `--no-dedupe` | No deduplica por `id_caso`. |
| `--quiet` | No imprime el progreso por chunk. |

Ejemplo de salida:

```
Ingesta completada
  run_id:           20261023T132729Z-b3b705
  filas leídas:     6,390,971
  filas válidas:    6,390,971
  filas rechazadas: 0
  duplicados:       0
  duración:         81.62 s
  memoria pico:     811.18 MB (límite 1024 MB)
  salida:           backend/data/processed/casos
  manifiesto:       backend/data/processed/manifests/ingesta_....json
```

## Resultado de la capa procesada

```
backend/data/processed/
├── casos/
│   ├── anio=2020/casos.parquet     (1.642.802 filas)
│   ├── anio=2021/casos.parquet     (3.514.639 filas)
│   ├── anio=2022/casos.parquet     (1.187.674 filas)
│   ├── anio=2023/casos.parquet        (42.030 filas)
│   └── anio=2024/casos.parquet         (3.826 filas)
├── rechazados/                     (solo si hay filas descartadas)
└── manifests/
    └── ingesta_<run_id>.json
```

Cada archivo contiene exactamente las 15 columnas finales:

```python
COLUMNAS_FINALES = [
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
]
```

Lectura desde Pandas (la partición aparece como columna virtual `anio`):

```python
import pandas as pd

casos = pd.read_parquet("backend/data/processed/casos")
print(casos.shape)
print(casos.groupby("anio").size())
```

En la corrida de referencia: **6.390.971 filas**, **33 departamentos**,
**1.121 códigos de municipio**, **59 MB** en Parquet (desde 1,4 GB) y
**0 rechazos**. Los detalles de cada transformación están en
[`backend/docs/diccionario_datos.md`](backend/docs/diccionario_datos.md).

## API

```bash
cd backend
uvicorn app.main:app --reload
```

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio. |
| `POST` | `/api/v1/ingesta` | Inicia la ingesta en segundo plano (202). |
| `GET` | `/api/v1/ingesta/estado` | Estado del job y último manifiesto. |
| `GET` | `/api/v1/ingesta/manifiestos?limite=10` | Historial de corridas. |

Ejemplo:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ingesta \
  -H "Content-Type: application/json" \
  -d '{"chunk_size": 100000, "memory_limit_mb": 1024, "overwrite": true}'

curl http://127.0.0.1:8000/api/v1/ingesta/estado
```

La documentación interactiva está en `http://127.0.0.1:8000/docs`.

## Criterios de aceptación

| Criterio | Implementación |
|---|---|
| Leer el archivo en bloques (ej. 100.000 filas) | `pd.read_csv(..., chunksize=chunk_size)` (o `pd.read_json(..., lines=True, chunksize=...)` para JSON Lines) en `pipeline._iter_chunks`; valor por defecto 100.000. |
| No superar el umbral de RAM | `usecols`, tipos compactos, escritura incremental, dedupe con memoria acotada y `MemoryMonitor` que aborta al superar el límite. Pico medido: 811 MB con límite de 1.024 MB. |
| Normalizar y limpiar el dataset | `cleaner.py`: encabezados a `snake_case`, fechas, DIVIPOLA, edad en años, sexo/categorías y reglas de rechazo. |
| Conservar solo columnas esenciales | 15 columnas finales; el resto se descarta al leer (`usecols`). |
| Cargar sin saturar el servidor | Staging + publicación atómica; filas inválidas separadas en `rechazados/`; manifiesto con métricas. |

## Pruebas

```bash
cd backend
python -m pytest
ruff check app scripts tests
```

Las pruebas cubren normalización, rechazos, deduplicación entre chunks,
particionado, límites de memoria, esquema incompleto, JSON Lines y endpoints
básicos (incluida una ingesta en segundo plano).

## Documentación

- [Diccionario de datos](backend/docs/diccionario_datos.md)
- [Arquitectura de la ingesta](backend/docs/arquitectura_ingesta.md)

## Próximos pasos

1. Cargar el Parquet limpio a PostgreSQL o MongoDB en lotes.
2. Crear endpoints de indicadores: series temporales, departamentos,
   municipios, edad, letalidad y recuperación.
3. Construir el frontend del dashboard.
4. Programar ingestas automáticas y monitoreo.
