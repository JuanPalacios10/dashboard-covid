# Arquitectura de la ingesta (fase 1)

## Flujo

```
CSV / JSON Lines local (1,4 GB)
    │
    ▼
pd.read_csv(..., usecols=16, dtype=str, chunksize=100_000)
   (o pd.read_json(..., lines=True, chunksize=100_000))
    │  una iteración = un chunk
    ▼
clean_chunk()  ── normaliza nombres, fechas, códigos, edad, categorías
    │             valida y separa filas rechazadas
    ▼
IdDeduplicator() ── deduplica id_caso dentro y entre chunks
    │
    ├──► ParquetPartitionWriter (casos)     → casos/anio=AAAA/casos.parquet
    └──► ParquetPartitionWriter (rechazos)  → rechazados/rechazados.parquet
    │
    ▼
staging/.staging-<run_id>/  ──► publicación atómica en data/processed/
    │
    ▼
manifests/ingesta_<run_id>.json  (métricas de calidad y memoria)
```

## Cómo se cumple el criterio de memoria

| Técnica | Efecto |
|---|---|
| `chunksize=100_000` | Solo se materializa un bloque a la vez. |
| `usecols` con 16 columnas | El parser no crea las 7 columnas descartadas. |
| `dtype=str` | Evita inferencia y copias intermedias; Pandas 3 usa strings respaldados por Arrow. |
| Tipos finales compactos (`int16`, `date32`, `string`) | Menos bytes por fila en memoria y en disco. |
| Escritura incremental por row group | No se acumulan todos los chunks para escribir al final. |
| Deduplicación con arreglo ordenado + búfer | Evita un `set` de Python de cientos de MB. |
| `pyarrow.default_memory_pool().release_unused()` por chunk | Devuelve buffers retenidos por el allocator. |
| `MemoryMonitor` (hilo cada 50 ms) | Registra el pico real y aborta si se supera el umbral. |

El umbral se configura con `--memory-limit-mb` o `COVID_MEMORY_LIMIT_MB`
(1.024 MB por defecto). Si se supera, el proceso lanza
`MemoryLimitExceeded`, **no publica** la capa procesada y deja un manifiesto en
estado `fallido`.

### Ajuste fino

- Servidor con poca RAM: baje `--chunk-size` a 50.000 y el umbral a 512 MB.
- Equipo con holgura: suba el chunk a 250.000 para reducir iteraciones.
- El límite debe quedar por encima del uso base de Python + Pandas (~180 MB en
  la medición) y del pico de un chunk.

## Publicación atómica

La ingesta escribe primero en `data/processed/.staging-<run_id>/`. Solo si todo
termina correctamente:

1. se elimina la capa anterior (si `--overwrite`),
2. se renombra `casos` y `rechazados` a su ubicación definitiva,
3. se escribe el manifiesto.

Si falla, el staging se elimina (salvo `--keep-staging`) y los datos anteriores
quedan intactos. Un lock de archivo (`.ingest.lock`) y un lock en proceso
impiden dos ingestas simultáneas.

## Idempotencia y duplicados

- La deduplicación es global y conserva la **primera** aparición del
  `id_caso`. El resto se envía a rechazados con motivo `id_caso duplicado`.
- `--no-dedupe`/`COVID_DEDUPLICATE=false` desactiva esta regla.
- Volver a ejecutar con `--overwrite` reconstruye la capa desde cero; el
  manifiesto conserva el historial de corridas.

## Persistencia y agregados del tablero

Cuando `COVID_MONGO_ENABLED=true`, la ingesta escribe los casos en
`casos_covid` y, al finalizar, reconstruye los agregados desde la capa Parquet
de staging, antes de publicarla:

- `resumen_diario_municipios`: totales por fecha y municipio.
- `kpis_gerenciales`: un documento acumulado (`_id = "nacional"`) y un
  documento por año (`_id = "2020"` … `_id = "2024"`).
- `dashboard_agregados`: series nacionales y por departamento, territorios,
  demografía y mapa de calor.

### Definiciones históricas

Para que los activos sean históricos y no un residual del estado actual:

- **Fallecido**: `fecha_muerte` no nula y menor o igual al corte.
- **Recuperado**: `fecha_recuperacion` no nula y menor o igual al corte, sin
  `fecha_muerte` anterior o igual al corte.
- **Activo**: sin ninguna de las dos fechas terminales antes o igual al corte.

En la vista por año se usa la cohorte de casos reportados en ese año y su
estado al cierre del año. En la vista acumulada se usa el corte real del
dataset (`2024-01-17`). Esto cambia las cifras frente a un residual por
estado: al corte acumulado quedan 184.393 fallecidos, 6.203.632 recuperados y
2.946 activos.

La consulta de la API nunca agrega `casos_covid` en tiempo de request: cada
endpoint lee uno o pocos documentos por `_id` en `kpis_gerenciales` o
`dashboard_agregados`.

Para cargar la capa Parquet existente sin reejecutar la ingesta:

```bash
python scripts/load_parquet_to_mongo.py --reset
```

Para recalcular solo los agregados desde Parquet:

```bash
python scripts/load_parquet_to_mongo.py --skip-load
```

## API

`app/api/routes.py` expone un job en segundo plano:

- `POST /api/v1/ingesta` inicia la ingesta (202) y devuelve el estado inicial.
- `GET /api/v1/ingesta/estado` devuelve el job actual y el último manifiesto.
- `GET /api/v1/ingesta/manifiestos?limite=10` lista corridas recientes.
- `GET /api/v1/kpis/gerenciales?anio=2021` devuelve los KPIs nacionales del
  período (`acumulado` o `2020`–`2024`). Requiere JWT con rol `admin`,
  `analista` o `ejecutivo`.
- `GET /api/v1/dashboard?anio=2021&departamento=05` devuelve el tablero
  compuesto (KPIs, series, territorios, demografía y calor) desde
  `dashboard_agregados`. Requiere el mismo control de roles.

El estado del job vive en memoria del proceso; el resultado durable es el
manifiesto JSON. Para despliegues con varios workers se recomienda mover el
estado a Redis/DB o ejecutar la ingesta como tarea de un worker dedicado.

## Siguiente fase (fuera de alcance)

1. Programación de ingestas (cron/worker) y monitoreo.
2. Filtros municipales detallados y comparación entre municipios.
3. Proyecciones, informes PDF y microdatos con endpoints propios.
