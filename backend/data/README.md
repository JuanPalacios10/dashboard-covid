# Datos locales

Esta carpeta no se versiona (el dataset pesa ~1,4 GB). Coloque aquí el archivo:

```
Casos_positivos_de_COVID-19_Colombia.csv
```

También se crea `processed/` con la capa Parquet limpia y los manifiestos de
cada ingesta. Ambos están excluidos por `.gitignore`.

Puede indicar otra ruta con la variable `COVID_DATASET_PATH`.
