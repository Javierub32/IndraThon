# Revisión frente al reto

La solución implementa los dos niveles y comparte motor entre API y cuadernos. La auditoría añadió filtros de fondo, barreras de incertidumbre, contraste contextual activo, comprobación geométrica, escala métrica y evaluación reproducible. No se utilizan nombres de escenas, coordenadas particulares ni ajustes por incidente en el algoritmo.

| Criterio | Implementación y evidencia | Límite pendiente |
|---|---|---|
| Zona afectada y perímetro | Reconstrucción con dos umbrales, limpieza, refinamiento acotado, polígonos con huecos y superposición sobre True Color/SWIR | Referencias manuales para medir IoU, Dice y contorno |
| Posible fuego activo | Regla cromática inspirada en SWIR, contraste local, crecimiento limitado y componentes; magenta independiente del naranja | JPEG sin bandas/render verificados; candidatos sin confirmación térmica |
| Falsos positivos | Agua/vegetación concordantes, veto de semillas en superficies claras, exclusión de incertidumbre antes de crecer, filtro contextual y motas | No existe una clasificación fiable de suelo/urbano/nubes con estos RGB. Pueden persistir errores |
| Robustez y automatización | Parámetros comunes, reserva de memoria antes de decodificar, límites de entrada, transparencia, abstención en SWIR uniforme y comprobación ORB/RANSAC | El encuadre no siempre es verificable; no se registra automáticamente. Mayor sensibilidad del avanzado al brillo |
| Calidad técnica | Módulos compartidos, contrato de etiquetas, JSON descargables y pruebas de API/algoritmo | Ejecutar un solo worker para coordinar la retención y concurrencia |
| Representación | Capas independientes, naranja/magenta/cian, pequeños puntos magenta sin halos grandes, calidad explicada, medidas y pasos intermedios | Revisar zonas ocultas; ausencia de candidato no prueba ausencia de incendio |
| Originalidad | Combinación explicable de evidencia entre composiciones, crecimiento con restricciones y contraste contextual; comparación con/sin filtro | Es una adaptación clásica, no un método científicamente validado nuevo |
| Generalización | Manifiesto extensible, configuración común, hashes, particiones development/holdout y evaluación con referencias | Las tres escenas ya vistas son desarrollo. No se acredita generalización por medir estabilidad |

## Escala de las imágenes

La resolución declarada es **20 m por píxel original cuadrado**: 400 m² = 0,04 ha. Se compensa el tamaño de análisis en ambos ejes antes de calcular hectáreas y metros. Los JSON registran esa procedencia. Si el exportador ha remuestreado el JPEG, debe actualizarse `pixel_size_m`; los archivos actuales no permiten verificar la escala o obtener coordenadas geográficas.

El perímetro es la suma de contornos exteriores en la cuadrícula de análisis trasladada al original; los huecos se exportan y se excluyen del área. Su longitud depende del detalle de segmentación y no equivale a una medición de campo.

## Qué se ha medido

`latest/report.md` contiene los resultados ejecutados, la comparación de candidatos con/sin contexto y las pruebas de brillo, JPEG y escala. Las máscaras de referencia no están disponibles, por lo que IoU/Dice de exactitud, precisión, recall y falsos positivos reales quedan sin calcular. Las reducciones de candidatos no se presentan como mejora medida de precisión.

Los controles automatizados de fondos son sintéticos: verifican regresiones concretas en agua, vegetación, suelo claro, urbano, nube y humo. No acreditan tasas de error en territorio real. Madrid–Ávila muestra inestabilidad de focos ante brillo; debe revisarse con referencias o bandas originales antes de afirmar una detección robusta.

## Protocolo para demostrar generalización

1. Conseguir incidentes nuevos y escenas negativas de territorios/fechas distintos; reservar incidentes completos como holdout antes de revisar resultados.
2. Anotar por separado superficie afectada y evidencia de actividad en la fecha de adquisición; usar 255 para zonas no observables o ambiguas. No convertir Wildfires en verdad terreno.
3. Congelar código, render esperado y configuración. Declarar cuadrícula y escala de cada entrada; evitar mezclar exportaciones con histogramas o canales diferentes.
4. Ejecutar el evaluador con referencias, reportar métricas por incidente y por clases de fondo. Revisar falsas detecciones y omisiones de focos, incluyendo escenas sin incendio.
5. Mantener resultados del holdout fuera de los ajustes. Si se cambia el método tras inspeccionarlos, reservar otro conjunto para la siguiente comprobación.

Las mejoras que requieren datos adicionales son validación de bandas/render, reflectancias originales, georreferenciación y una referencia independiente. No pueden inferirse con fiabilidad a partir de estos JPEG.
