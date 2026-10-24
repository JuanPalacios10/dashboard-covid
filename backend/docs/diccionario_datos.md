# Diccionario de datos — capa procesada

La salida de la ingesta contiene exactamente las 15 columnas solicitadas. Los
nombres se normalizaron a `snake_case` (sin tildes ni espacios), los tipos se
fijaron de forma explícita y los valores se estandarizaron.

## Columnas finales

| Columna final | Columna original | Tipo | Regla aplicada |
|---|---|---|---|
| `fecha_reporte_web` | `fecha reporte web` | `date32` | Fecha sin hora. Si no se puede interpretar, la fila se rechaza. Es la clave de partición por año. |
| `id_caso` | `ID de caso` | `int64` | Se eliminan separadores de miles (`.`, `,`, espacios) y se valida que sea entero. Si es inválido, la fila se rechaza. |
| `fecha_notificacion` | `Fecha de notificación` | `date32` | Fecha sin hora; valor inválido queda nulo y se reporta. |
| `codigo_divipola_departamento` | `Código DIVIPOLA departamento` | `string(2)` | Se quitan puntos/espacios y se rellena con ceros (`5` → `05`). Si el campo trae un código municipal (`8.001`), se toma el prefijo departamental (`08`). |
| `nombre_departamento` | `Nombre departamento` | `string` | Mayúsculas, espacios colapsados y nombre canónico DANE según el código (por ejemplo, `BARRANQUILLA` → `ATLÁNTICO`, `BOGOTA` → `BOGOTÁ D.C.`). |
| `codigo_divipola_municipio` | `Código DIVIPOLA municipio` | `string(5)` | Se quitan puntos/espacios y se rellena a 5 dígitos (`8.001` → `08001`). |
| `nombre_municipio` | `Nombre municipio` | `string` | Mayúsculas y espacios colapsados; se conservan tildes. |
| `edad` | `Edad` + `Unidad de medida de edad` | `int16` | Se convierte siempre a **años cumplidos**: unidad 1 = años, 2 = meses (`/12`), 3 = días (`/365.25`), truncando al entero. Rango válido 0–120. |
| `sexo` | `Sexo` | `string` | `M`/`F` (también acepta `Masculino`/`Femenino`); `I` si viene indeterminado. Un valor desconocido se deja nulo y se cuenta como inválido. |
| `tipo_contagio` | `Tipo de contagio` | `string` | Etiquetas canónicas `Comunitaria`, `Relacionado`, `Importado`; una categoría nueva se conserva en formato título y se reporta. |
| `recuperado` | `Recuperado` | `string` | Etiquetas canónicas `Recuperado`, `Fallecido`, `Activo`; los nulos se conservan y se reportan. |
| `fecha_inicio_sintomas` | `Fecha de inicio de síntomas` | `date32` | Fecha sin hora; valor inválido queda nulo y se reporta. |
| `fecha_muerte` | `Fecha de muerte` | `date32` | Fecha sin hora; nula en la mayoría de casos (personas no fallecidas). |
| `fecha_diagnostico` | `Fecha de diagnóstico` | `date32` | Fecha sin hora. |
| `fecha_recuperacion` | `Fecha de recuperación` | `date32` | Fecha sin hora. |

> La columna original `Unidad de medida de edad` se usa para normalizar `edad`
> y luego se descarta porque no hace parte del contrato final.

## Columnas descartadas y motivo

Se ignoran 8 columnas del archivo original: `Unidad de medida de edad` (ya
aplicada), `Ubicación del caso`, `Estado`, `Código ISO del país`,
`Nombre del país`, `Tipo de recuperación`, `Pertenencia étnica` y
`Nombre del grupo étnico`. No son necesarias para los indicadores principales
ni para la geolocalización/tiempo del dashboard, y su inclusión incrementaría
el tamaño y la complejidad de la capa procesada.

## Reglas de rechazo

Una fila se envía a `data/processed/rechazados/` cuando no puede cargarse de
forma confiable. La columna `motivo_rechazo` puede contener uno o varios
motivos separados por `; `:

| Motivo | Condición |
|---|---|
| `id_caso inválido` | Falta, no es numérico o no es entero. |
| `fecha_reporte_web inválida` | Falta o no se puede interpretar; es obligatoria para particionar. |
| `código DIVIPOLA departamento inválido` | No tiene 1–5 dígitos o no se puede normalizar a 2 dígitos. |
| `código DIVIPOLA municipio inválido` | No tiene 1–5 dígitos o no se puede normalizar a 5 dígitos. |
| `edad inválida` | Falta, no es numérica, es negativa o supera 120 años. |
| `id_caso duplicado` | Ya apareció en el mismo chunk o en uno anterior (se conserva la primera aparición). |

Los rechazados incluyen las 15 columnas (con los valores ya normalizados hasta
donde fue posible), `motivo_rechazo` y `anio_reporte`.

## Calidad reportada (no rechaza filas)

El manifiesto JSON registra, entre otros:

- nulos por columna en la salida,
- fechas futuras,
- códigos de departamento desconocidos,
- municipios cuyo prefijo no coincide con el departamento,
- `muerte_con_estado_no_fallecido` (hay fecha de muerte pero `recuperado` no es `Fallecido`),
- `fallecido_sin_fecha_de_muerte`,
- `muerte_antes_de_sintomas`, `recuperacion_antes_de_sintomas`,
- `diagnostico_antes_de_sintomas`,
- edades convertidas desde meses/días,
- categorías observadas y cantidad de casos por departamento.

## Resultado de referencia

Última corrida completa sobre el archivo entregado:

| Métrica | Valor |
|---|---|
| Filas leídas / publicadas | 6.390.971 / 6.390.971 |
| Filas rechazadas | 0 |
| Duplicados por `id_caso` | 0 |
| Departamentos | 33 |
| Códigos de municipio distintos | 1.121 |
| Nulos en `recuperado` | 36.327 |
| Nulos en `fecha_muerte` | 6.206.578 |
| Tamaño Parquet (zstd) | ~59 MB (desde 1,4 GB) |
| Duración | ~82 s (chunk de 100.000 filas) |
| Pico de RAM | ~811 MB (límite 1.024 MB) |

> La partición `anio=AAAA` aparece al leer el directorio con Pandas/PyArrow,
> pero no se almacena como columna física dentro de cada archivo.
