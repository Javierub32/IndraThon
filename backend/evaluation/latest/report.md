# Evaluación reproducible

La estabilidad mide consistencia ante perturbaciones, no precisión. Sin referencias independientes no se mide generalización.

Escala declarada: 20 m/píxel original; se compensa el remuestreo. Área y perímetro son estimados.

| Escena | Partición | Regiones | Área ha | Perímetro km | Focos sin/con contexto | Referencias |
|---|---|---:|---:|---:|---|---|
| niebla | development | 11 | 7148.4 | 212.1 | 44/36 | affected: not_provided, active: not_provided |
| la-mierla | development | 14 | 14424.8 | 340.6 | 195/65 | affected: not_provided, active: not_provided |
| madrid-avila | development | 16 | 93995.2 | 1176.9 | 388/207 | affected: not_provided, active: not_provided |

## Estabilidad (IoU respecto al resultado original, no exactitud)

| Escena | Perturbación | Cicatriz | Focos |
|---|---|---:|---:|
| niebla | brightness_0.9 | 0.988 | 0.940 |
| niebla | brightness_1.1 | 0.992 | 0.778 |
| niebla | jpeg_quality_70 | 0.928 | 0.759 |
| niebla | scale_075 | 0.966 | 0.844 |
| la-mierla | brightness_0.9 | 0.995 | 0.798 |
| la-mierla | brightness_1.1 | 0.995 | 0.882 |
| la-mierla | jpeg_quality_70 | 0.930 | 0.609 |
| la-mierla | scale_075 | 0.964 | 0.755 |
| madrid-avila | brightness_0.9 | 0.992 | 0.414 |
| madrid-avila | brightness_1.1 | 0.987 | 0.555 |
| madrid-avila | jpeg_quality_70 | 0.893 | 0.511 |
| madrid-avila | scale_075 | 0.969 | 0.887 |

Los pares con ambas máscaras vacías tienen estabilidad 1; no acreditan detección correcta.
Las escenas de desarrollo no son un conjunto de validación independiente. Mantener umbrales fijos y separar incidentes nuevos como holdout antes de observar sus resultados.
El humo puede ocultar focos. El contraste local puede perder frentes extensos. Suelo rojo y superficies urbanas pueden seguir generando candidatos.
La exactitud se calcula solo cuando el manifiesto incluye referencias manuales independientes; Wildfires no es una referencia cuantitativa.
Revisar estabilidad en madrid-avila (IoU < 0,6): brightness_0.9/active, brightness_1.1/active, jpeg_quality_70/active.
