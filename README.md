# Brasa · Detección de incendios por satélite

FastAPI + React para delimitar superficies afectadas y detectar candidatos de fuego activo en composiciones JPEG/PNG/WebP de Sentinel-2. Incluye las escenas de Niebla, La Mierla y Madrid–Ávila, subida de composiciones propias y cuadernos de exploración paso a paso.

## Arranque con Docker

Desarrollo, desde la raíz:

```powershell
docker compose -f compose.dev.yaml up --build
```

Interfaz: http://localhost:5174. API: http://localhost:8001/docs.

Producción local:

```powershell
docker compose up --build
```

Interfaz: http://localhost:5173. API: http://localhost:8000/docs. El contenedor de producción conserva los resultados mientras exista; recrearlo elimina los resultados almacenados en él. Las imágenes originales están incluidas en la imagen Docker.

## Arranque sin Docker

Backend, desde la raíz y con tu entorno Python activado:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Frontend, en otra terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Vite utiliza `http://127.0.0.1:8000` por defecto. Para otro puerto, establece `VITE_API_TARGET` antes de iniciarlo. Docker configura el nombre interno `backend` mediante esa variable.

## Cuaderno temporal

`backend/temporal_segmentacion.ipynb` contiene gráficos y salidas ejecutados para delimitar la cicatriz. `backend/temporal_fuego_activo.ipynb` recorre el detector avanzado y compara el mapa con la composición `Wildfires` disponible como referencia visual. Ninguno trata esa composición como una máscara cuantitativa. Para repetirlos, selecciona un kernel del entorno del proyecto e instala:

```powershell
python -m pip install -r backend/requirements-dev.txt
```

Puedes abrirlos en VS Code u otro editor de Jupyter. Cambia `SCENE` entre `Niebla`, `La_Mierla` y `Madrid-Avila` y ejecuta las celdas. Funcionan desde la raíz o desde `backend`. El cuaderno de cicatriz muestra características, umbrales, crecimiento, limpieza y perímetros. El avanzado añade semillas cromáticas, apoyo contextual, crecimiento limitado y mapa magenta sobre la cicatriz naranja. `backend/temporal_evaluacion.ipynb` presenta las tres escenas, la estabilidad y el protocolo de referencias independientes.

La celda de evaluación admite referencias independientes en `backend/references/<SCENE>.png`: 0=fondo, 1=afectado, 255=ignorar. La referencia debe compartir la cuadrícula final. Cuando no hay referencia no se inventan métricas de exactitud. `EXPORT=True` guarda los resultados del cuaderno dentro de `backend/results/notebook_<SCENE>`.

## Algoritmo y convenciones

1. Decodificación acotada a 4096 píxeles en el lado mayor; se conservan las dimensiones originales. JPEG usa subsampling durante la decodificación cuando es posible.
2. Primera detección a 1024/1536/2048 píxeles desde la interfaz (API: 256–3072).
3. Evidencia de color con predominio rojo/verde, cromaticidad Lab y saturación, usando escalas fijas entre escenas.
4. Exclusión conservadora de agua/vegetación concordantes entre composiciones. Las superficies claras o rojizas en True Color no pueden iniciar regiones, aunque pueden incorporarse como candidatos conectados a semillas. Se excluyen humo/nube estimados y falta de datos **antes** del crecimiento. Dos umbrales y reconstrucción con conectividad de ocho que contengan semillas.
5. Cierre pequeño, tamaño mínimo relativo y relleno de huecos pequeños. Se conservan huecos grandes y zonas inciertas.
6. Refinamiento opcional en una banda alrededor de los límites, a hasta el doble de resolución inicial y con máximo de 4096. Las características se calculan por bloques.
7. Contornos exteriores e interiores. Coordenadas `[x,y]`, origen arriba a la izquierda, expresadas respecto a la imagen original. El perímetro suma solo los límites exteriores; los huecos se exportan por separado.

Todos los arrays de imagen internos son RGB. `mask.png` contiene 0/255 y es una máscara binaria de la detección. `labels.png` contiene 0=fondo, 1=afectado y 255=incierto/no evaluable. Las máscaras están en `analysis_size`, no necesariamente en el tamaño original; `regions.json` contiene ambos tamaños. Las cifras en píxeles originales son estimaciones obtenidas a partir de la resolución de análisis.

La máscara de incertidumbre combina brillo y baja saturación en True Color con respuesta cian en SWIR, además de blancos ambiguos. Es una heurística visual y puede confundir superficies claras con humo. Los PNG transparentes se componen sobre negro, considerado sin datos; se exige cobertura en ambas imágenes. Una imagen SWIR espacialmente uniforme se marca como incierta y no genera una detección de todo el encuadre.

Se rechazan dimensiones originales distintas. ORB sobre gradientes y RANSAC comprueban el encuadre cuando existen suficientes correspondencias; una transformación incompatible produce error. Si no hay textura suficiente se indica «revisar», sin afirmar que las imágenes estén alineadas. No se corrigen desplazamientos automáticamente. `quality.json` y el visor explican cobertura, saturación, correspondencia e incertidumbre; estas comprobaciones no son una puntuación de exactitud.

### Escala Sentinel: 20 metros por píxel

Se utiliza la resolución **declarada por el usuario de 20 m por píxel original cuadrado**. Cada píxel representa 400 m² = 0,04 ha. Para una máscara reducida, el área se calcula como `píxeles_detectados × (ancho_original/ancho_máscara) × (alto_original/alto_máscara) × pixel_size_m²`. Los segmentos del contorno se escalan primero en x/y a la imagen original y después a metros. El visor muestra hectáreas y kilómetros, y los JSON conservan también píxeles, metros y la procedencia declarada de la escala.

El campo `pixel_size_m` vale 20 por defecto y puede ajustarse si una exportación tiene otra escala. Los JPEG no contienen información suficiente para verificarla: estas medidas dependen de que el render conserve esos 20 m/px. No se calculan temperatura ni coordenadas terrestres. El perímetro exterior y el área dependen de la resolución de análisis; no son mediciones topográficas.

### Fuego activo

La interfaz calcula la segmentación y el fuego activo en un solo análisis. En el visor, los controles independientes «Segmentación» y «Posible fuego activo» permiten mostrar cualquiera de las dos capas, ambas o ninguna sin volver a analizar. Desactivar la segmentación oculta su relleno y su perímetro. Los focos conservan únicamente un pequeño marcador magenta, sin círculos blancos. `labels.png` mantiene su codificación básica. La descarga `active_labels.png` usa 0=fondo, 1=superficie afectada sin candidato activo, 2=fuego activo posible y 255=incierto/sin datos. `hotspots.json` y `fire_mask.png` guardan centros, cajas y máscaras en coordenadas de imagen.

El detector adapta las Ecs. 2–4 del SWIR-rule de Mitra et al. (arXiv:2609.16199v1): aproxima B12 y B8A invirtiendo los límites publicados del render fijo para SWIR RGB B12/B11/B8A; aplica semillas B12≥0,35 y B12/B8A≥4; candidatos B12≥0,25 y B12/B8A≥2. El orden de bandas y el render de los JPEG suministrados no están verificados. Los umbrales publicados operan sobre reflectancias antes del render; su inversión desde JPEG es aproximada y no reproduce esa medición.

El filtro contextual exige que un componente de semillas tenga apoyo de brillo local: diferencia de rojo ≥0,08 y z≥1,5 frente al fondo, con suelo de ruido 0,015 y al menos 25% de fondo en una ventana de radio relativo 0,015 al lado mayor (mínimo 5 píxeles). El fondo excluye semillas e incertidumbre. Después se crece dos pasos con conectividad 4 y se eliminan componentes de un solo píxel. Los parámetros son comunes a todas las escenas. Este filtro descarta rojo uniforme, pero puede omitir frentes extensos y mantener terrenos rojos con bordes brillantes. Se exportan las semillas iniciales y el apoyo contextual para revisar la decisión.

Los marcadores significan evidencia cromática compatible, no temperatura ni confirmación de combustión. En avanzado se excluyen píxeles inciertos. La sensibilidad ajusta la cicatriz, mientras que los umbrales activos permanecen fijos.

La puntuación de color no es una probabilidad calibrada. Pueden persistir falsos positivos en terrenos rojizos, zonas agrícolas o urbanas; el humo puede ocultar superficie afectada. Las tres escenas se han inspeccionado visualmente con una configuración común. No existe aún una referencia manual independiente que permita afirmar precisión, IoU o generalización a nuevas escenas.

## API

- `GET /api/health`: estado.
- `GET /api/scenes`: escenas disponibles.
- `GET /api/scenes/{id}/preview/{true-color|swir|wildfires}`: miniatura de una composición disponible.
- `POST /api/scenes/{id}/analyze`: JSON con `max_side`, `sensitivity`, `min_area_fraction`, `closing_radius`, `refine`, `active_fire`, `pixel_size_m` (20 por defecto).
- `POST /api/process`: multipart, `image1`=True Color, `image2`=SWIR; campos `sensitivity`, `max_side`, `refine`, `active_fire`, `pixel_size_m`.
- `GET /api/results/{result_id}/{artifact}`: imagen, máscara, geometría o metadatos.

Máximo 80 MB por archivo y 85 megapíxeles originales. Los resultados se almacenan en `backend/results`; se conservan los últimos 20 análisis de la API. El cuaderno y el navegador usan la misma implementación de `processing`. Un análisis simultáneo por proceso; otra petición de procesamiento recibe 409. Ejecutar con un único worker para mantener ese límite y la retención coordinados.

## Verificación

```powershell
python -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm run lint
```

Las pruebas cubren reconstrucción y barreras de incertidumbre, ejemplos sintéticos de fondos problemáticos, contraste activo, crecimiento limitado, abstención en imágenes uniformes, transparencia, desalineación, escala métrica tras remuestreo, evaluación y contratos de API. La reserva de procesamiento ocurre antes de decodificar para limitar la memoria de solicitudes concurrentes. Los controles sintéticos no sustituyen la validación con imágenes reales etiquetadas.

## Evaluación reproducible

Desde la raíz:

```powershell
python backend/evaluate.py --robustness
```

`backend/evaluation/manifest.json` fija la configuración común y las tres escenas de desarrollo. `backend/evaluation/latest/report.md` resume medidas y estabilidad; `report.json` incluye hashes de entradas/código/configuración, comprobaciones y métricas. Se comprueban brillo ±10%, recompresión JPEG a calidad 70 y reducción a 75%. La IoU contra la propia salida original mide **consistencia**, no exactitud; valores menores que 0,6 se señalan para revisión. La comparación con/sin contexto mide cuántos candidatos se filtran, sin denominarlos falsos positivos reales.

Para escenas nuevas, añade entradas con `split: "holdout"` y rutas relativas al manifiesto. Congela configuración antes de mirar esos resultados. Referencias opcionales por escena:

```json
"references": {
  "affected": {"path": "references/incidente_affected.png", "grid": "original"},
  "active": {"path": "references/incidente_active.png", "grid": "analysis"}
}
```

Referencias de un canal, valores 0=fondo, 1=objetivo, 255=ignorar. La cuadrícula declarada debe coincidir exactamente. `original` se remuestrea mediante vecino más cercano al tamaño de análisis y esa operación se registra. Se calculan IoU, Dice, precisión, recall y F1 de contorno (tolerancia 2 píxeles de análisis); para focos también se emparejan componentes uno a uno (conectividad 8, IoU≥0,1, máxima cardinalidad). Las divisiones sin denominador dan `null`. Incluir escenas negativas permite contar falsas detecciones.

Actualmente no hay referencias independientes ni incidentes reservados sin observar. La calidad cuantitativa y la generalización quedan **pendientes de medición**. Véase `backend/evaluation/EVALUACION.md` para relacionar requisitos, evidencia y limitaciones.

## Reparto del equipo

| Persona | Módulos | Responsabilidad |
|---|---|---|
| 1 | `backend/processing/features.py`, `segmentation.py`, `active_fire.py` | Evidencia cromática de cicatriz y regla SWIR de fuego activo |
| 2 | `backend/processing/geometry.py`, `evaluation.py` | Limpieza, perímetros y evaluación independiente |
| 3 | `backend/main.py`, `processing/io.py`, `pipeline.py`, Docker | API, entradas, rendimiento e integración |
| 4 | `frontend/src/` | Visor, formularios, capas, accesibilidad y exportación |

Los dos cuadernos son herramientas comunes para inspección. Acordad cambios de contrato antes de modificar campos, coordenadas, resoluciones o valores de etiquetas.
