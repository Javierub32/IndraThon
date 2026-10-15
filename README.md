# Detección de Fuegos · Reto INDRA Malackathon 2026

FastAPI + React para delimitar superficies con evidencia de afectación en composiciones JPEG/PNG/WebP de Sentinel-2. Incluye las escenas de Niebla, La Mierla y Madrid–Ávila, subida de composiciones propias y un cuaderno de exploración ejecutado.

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

`backend/temporal_segmentacion.ipynb` contiene gráficos y salidas ya ejecutados. Para repetirlo, selecciona un kernel del entorno del proyecto e instala:

```powershell
python -m pip install -r backend/requirements-dev.txt
```

Puedes abrirlo en VS Code u otro editor de Jupyter. Cambia `SCENE` entre `Niebla`, `La_Mierla` y `Madrid-Avila`, ajusta `CONFIG` y ejecuta todas las celdas. Funciona desde la raíz o desde `backend`. Muestra entradas, características, histograma, puntuación, semillas, candidatos, crecimiento, limpieza, incertidumbre, refinamiento, perímetros, sensibilidad y comparación entre escenas.

La celda de evaluación admite referencias independientes en `backend/references/<SCENE>.png`: 0=fondo, 1=afectado, 255=ignorar. La referencia debe compartir la cuadrícula final. Cuando no hay referencia no se inventan métricas de exactitud. `EXPORT=True` guarda los resultados del cuaderno dentro de `backend/results/notebook_<SCENE>`.

## Algoritmo y convenciones

1. Decodificación acotada a 4096 píxeles en el lado mayor; se conservan las dimensiones originales. JPEG usa subsampling durante la decodificación cuando es posible.
2. Primera detección a 1024/1536/2048 píxeles desde la interfaz (API: 256–3072).
3. Evidencia de color con predominio rojo/verde, cromaticidad Lab y saturación, usando escalas fijas entre escenas.
4. Dos umbrales: semillas fuertes y candidatos permisivos. Reconstrucción mediante componentes con conectividad de ocho que contengan semillas.
5. Cierre pequeño, tamaño mínimo relativo y relleno de huecos pequeños. Se conservan huecos grandes y zonas inciertas.
6. Refinamiento opcional en una banda alrededor de los límites, a hasta el doble de resolución inicial y con máximo de 4096. Las características se calculan por bloques.
7. Contornos exteriores e interiores. Coordenadas `[x,y]`, origen arriba a la izquierda, expresadas respecto a la imagen original. El perímetro suma solo los límites exteriores; los huecos se exportan por separado.

Todos los arrays de imagen internos son RGB. `mask.png` contiene 0/255 y es una máscara binaria de la detección. `labels.png` contiene 0=fondo, 1=afectado y 255=incierto/no evaluable. Las máscaras están en `analysis_size`, no necesariamente en el tamaño original; `regions.json` contiene ambos tamaños. Las cifras en píxeles originales son estimaciones obtenidas a partir de la resolución de análisis. No se calculan hectáreas, metros, temperatura ni coordenadas geográficas.

La máscara de incertidumbre combina brillo y baja saturación en True Color con respuesta cian en SWIR. Es una heurística visual y puede confundir superficies claras con humo. La correspondencia espacial se presupone a partir del mismo encuadre: el sistema rechaza dimensiones originales distintas, pero no registra las imágenes automáticamente.

La puntuación de color no es una probabilidad calibrada. Pueden persistir falsos positivos en terrenos rojizos, zonas agrícolas o urbanas; el humo puede ocultar superficie afectada. Las tres escenas se han inspeccionado visualmente con una configuración común. No existe aún una referencia manual independiente que permita afirmar precisión, IoU o generalización a nuevas escenas.

## API

- `GET /api/health`: estado.
- `GET /api/scenes`: escenas disponibles.
- `GET /api/scenes/{id}/preview/{true-color|swir|wildfires}`: miniatura de una composición disponible.
- `POST /api/scenes/{id}/analyze`: JSON con `max_side`, `sensitivity`, `min_area_fraction`, `closing_radius`, `refine`.
- `POST /api/process`: multipart, `image1`=True Color, `image2`=SWIR; campos `sensitivity`, `max_side`, `refine`.
- `GET /api/results/{result_id}/{artifact}`: imagen, máscara, geometría o metadatos.

Máximo 80 MB por archivo y 85 megapíxeles originales. Los resultados se almacenan en `backend/results`; se conservan los últimos 20 análisis de la API. El cuaderno y el navegador usan la misma implementación de `processing`. Un análisis simultáneo por proceso; otra petición de procesamiento recibe 409. Ejecutar con un único worker para mantener ese límite y la retención coordinados.

## Verificación

```powershell
python -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm run lint
```

Las pruebas cubren reconstrucción, ausencia de fuego, huecos y regiones múltiples, escalado, métricas con referencia ignorada, entradas incorrectas, contrato de subida y descarga, concurrencia y límites del borrado de resultados.

## Reparto del equipo

| Persona | Módulos | Responsabilidad |
|---|---|---|
| 1 | `backend/processing/features.py`, `segmentation.py` | Características, puntuación, semillas y candidatos |
| 2 | `backend/processing/geometry.py`, `evaluation.py` | Limpieza, perímetros y evaluación independiente |
| 3 | `backend/main.py`, `processing/io.py`, `pipeline.py`, Docker | API, entradas, rendimiento e integración |
| 4 | `frontend/src/` | Visor, formularios, capas, accesibilidad y exportación |

El cuaderno es la herramienta común para inspección. Acordad cambios de contrato antes de modificar campos, coordenadas, resoluciones o valores de etiquetas.
