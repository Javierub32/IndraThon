import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import indraLogoLightTheme from './assets/indra-logo-dark.svg';
import indraLogoDarkTheme from './assets/indra-logo.svg';
const ACCESSIBILITY_STORAGE_KEY = 'brasa.accessibility';
const DEFAULT_ACCESSIBILITY = {
  fontSize: 100,
  fontFamily: 'indra',
  theme: 'light',
  highContrast: false
};
const ACCESSIBLE_FONTS = ['indra', 'arial', 'verdana', 'georgia', 'opendyslexic'];
const number = value => new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 1
}).format(value);
const steps = [['swir', '01', 'Composición SWIR', 'Imagen de entrada utilizada para localizar señales de afectación.'], ['score', '02', 'Señales de color', 'Azul: evidencia baja. Amarillo: evidencia alta. Es una puntuación, no una probabilidad.'], ['seeds', '03', 'Zonas de referencia', 'Píxeles con señales visuales más claras.'], ['candidates', '04', 'Áreas candidatas', 'Superficies compatibles con las señales del análisis.'], ['grown', '05', 'Áreas conectadas', 'Candidatos próximos a zonas con señales claras.'], ['cleaned', '06', 'Límites depurados', 'Eliminación de ruido y relleno limitado de huecos.'], ['overlay', '07', 'Perímetro estimado', 'Resultado tras el ajuste opcional de los límites.']];
const activeFireSteps = [['fire_score', '08', 'Contraste de la imagen', 'Brillo y contraste del render. La equivalencia con bandas espectrales depende de la composición; no indica temperatura.'], ['fire_raw_seeds', '09', 'Primeras señales', 'Primer filtro de brillo y relación entre canales.'], ['fire_context', '10', 'Comparación del entorno', 'Compara las señales con el brillo de las zonas vecinas.'], ['fire_seeds', '11', 'Señales consistentes', 'Zonas candidatas con apoyo del entorno.'], ['fire_candidates', '12', 'Áreas candidatas', 'Píxeles compatibles con las señales detectadas.'], ['fire_grown', '13', 'Áreas agrupadas', 'Agrupación limitada de zonas próximas.'], ['fire_mask', '14', 'Posibles focos', 'Zonas con señales compatibles con actividad de fuego.']];
async function request(url, options) {
  const response = await fetch(url, options);
  const body = await response.text();
  let data;

  try {
    data = body ? JSON.parse(body) : {};
  } catch {
    const isHtml = response.headers.get('content-type')?.includes('text/html') || /^\s*</.test(body);
    if (isHtml) {
      throw new Error(`El servidor devolvió una página HTML en vez de JSON (HTTP ${response.status}). Comprueba que el backend esté activo y que la ruta /api esté configurada en Render.`);
    }
    const detail = body.trim().slice(0, 240);
    throw new Error(detail ? `${detail} (HTTP ${response.status}).` : `El servidor devolvió una respuesta no válida (HTTP ${response.status}).`);
  }

  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Revisa las imágenes y los parámetros del análisis.';
    throw new Error(detail);
  }
  return data;
}
function loadAccessibilitySettings() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(ACCESSIBILITY_STORAGE_KEY) || '{}');
    const fontSize = Number(saved.fontSize);
    return {
      fontSize: Number.isFinite(fontSize) ? Math.min(160, Math.max(100, fontSize)) : DEFAULT_ACCESSIBILITY.fontSize,
      fontFamily: ACCESSIBLE_FONTS.includes(saved.fontFamily) ? saved.fontFamily : DEFAULT_ACCESSIBILITY.fontFamily,
      theme: saved.theme === 'dark' ? 'dark' : DEFAULT_ACCESSIBILITY.theme,
      highContrast: saved.highContrast === true
    };
  } catch {
    return DEFAULT_ACCESSIBILITY;
  }
}
function loadMaskPixels(source) {
  if (!source) return Promise.resolve(null);
  return new Promise(resolve => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) return resolve(null);
      try {
        context.drawImage(image, 0, 0);
        const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
        const pixels = new Uint8Array(canvas.width * canvas.height);
        for (let index = 0; index < pixels.length; index += 1) {
          pixels[index] = rgba[index * 4] >= 128 ? 1 : 0;
        }
        resolve({ width: canvas.width, height: canvas.height, pixels });
      } catch {
        resolve(null);
      }
    };
    image.onerror = () => resolve(null);
    image.src = source;
  });
}
function pointInRing(x, y, ring) {
  let inside = false;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index, index += 1) {
    const [xi, yi] = ring[index];
    const [xj, yj] = ring[previous];
    const crosses = (yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / ((yj - yi) || Number.EPSILON) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}
function regionAtPoint(regions, x, y) {
  return regions.find(region => {
    const [left, top, width, height] = region.bbox || [0, 0, 0, 0];
    if (x < left || x > left + width || y < top || y > top + height) return false;
    return pointInRing(x, y, region.outer) && !region.holes.some(hole => pointInRing(x, y, hole));
  });
}
function Contours({
  result,
  selected,
  hoveredFeature,
  showPerimeter,
  showAffected
}) {
  const {
    width,
    height
  } = result.original_size;
  return <svg className="contour-layer" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    {result.regions.map(region => {
      const rings = [region.outer, ...region.holes];
      const path = rings.map(ring => `M${ring.map(p => p.join(',')).join('L')}Z`).join(' ');
      const hovered = hoveredFeature?.regionId === region.id;
      const active = hovered || selected === region.id;
      return <g key={region.id}>
        <path d={path} fill={showAffected && hoveredFeature?.type === 'affected' && hovered ? 'rgba(255,255,255,0.22)' : 'transparent'} fillRule="evenodd" stroke={showPerimeter ? active ? '#FFFFFF' : '#FFBB21' : 'none'} strokeWidth={active ? 3 : 1.5} vectorEffect="non-scaling-stroke" pointerEvents={showAffected ? 'fill' : 'none'} data-map-feature={showAffected ? 'affected' : undefined} data-region-id={region.id} />
        {showPerimeter && <path className="perimeter-hover-target" d={path} fill="none" stroke="transparent" strokeWidth="12" vectorEffect="non-scaling-stroke" pointerEvents="stroke" data-map-feature="perimeter" data-region-id={region.id} />}
      </g>;
    })}
  </svg>;
}
function FireMarkers({
  hotspots,
  originalSize,
  hoveredFeature
}) {
  return <svg className="fire-markers-layer" role="img" viewBox={`0 0 ${originalSize.width} ${originalSize.height}`} aria-label="Marcadores de posibles focos activos">
    {hotspots.map(hotspot => {
      const [x, y] = hotspot.centroid;
      const hovered = hoveredFeature?.type === 'fire' && hoveredFeature.hotspotId === hotspot.id;
      return <g key={hotspot.id} role="img" data-map-feature="fire" data-hotspot-id={hotspot.id} className={hovered ? 'fire-marker-hovered' : ''} aria-label={`Posible foco ${hotspot.id}; ${hotspot.seed_pixels} píxeles semilla`}>
        <circle className="fire-marker-hit-area" cx={x} cy={y} r="9" fill="transparent" stroke="transparent" vectorEffect="non-scaling-stroke" />
        <circle cx={x} cy={y} r={hovered ? 4 : 2.5} fill="#E3342F" stroke="#FFFFFF" strokeWidth={hovered ? 3 : 2.5} vectorEffect="non-scaling-stroke" pointerEvents="none" />
      </g>;
    })}
  </svg>;
}
function ResultViewer({
  result
}) {
  const imageStackRef = useRef(null);
  const imageViewportRef = useRef(null);
  const dragRef = useRef(null);
  const zoomRef = useRef(100);
  const wheelDeltaRef = useRef(0);
  const pendingZoomAnchorRef = useRef(null);
  const exportPanelContentRef = useRef(null);
  const [exportContentHeight, setExportContentHeight] = useState(null);
  const hasTrueColor = result.input_mode !== 'swir_only';
  const [base, setBase] = useState(hasTrueColor ? 'true-color' : 'swir');
  const [segmentation, setSegmentation] = useState(true);
  const [showFire, setShowFire] = useState(Boolean(result.active_fire?.enabled));
  const [perimeter, setPerimeter] = useState(true);
  const [uncertain, setUncertain] = useState(false);
  const [opacity, setOpacity] = useState(38);
  const [zoom, setZoom] = useState(100);
  const [isPanning, setIsPanning] = useState(false);
  const [selected, setSelected] = useState(null);
  const [maskCache, setMaskCache] = useState(null);
  const [hoveredFeature, setHoveredFeature] = useState(null);
  const [activeStep, setActiveStep] = useState('overlay');
  const fire = result.active_fire;
  useLayoutEffect(() => {
    const content = exportPanelContentRef.current;
    if (!content) return undefined;
    const updateHeight = () => setExportContentHeight(Math.ceil(content.getBoundingClientRect().height));
    updateHeight();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateHeight);
      return () => window.removeEventListener('resize', updateHeight);
    }
    const observer = new ResizeObserver(updateHeight);
    observer.observe(content);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    const anchor = pendingZoomAnchorRef.current;
    if (!anchor || anchor.zoom !== zoom) return;
    pendingZoomAnchorRef.current = null;
    const scale = anchor.zoom / anchor.previousZoom;
    anchor.viewport.scrollLeft = Math.max(0, anchor.contentX * scale - anchor.x);
    anchor.viewport.scrollTop = Math.max(0, anchor.contentY * scale - anchor.y);
  }, [zoom]);
  const maskCacheKey = `${result.assets.mask}|${result.assets.uncertainty}|${fire?.enabled ? result.assets.fire_mask : ''}`;
  useEffect(() => {
    let active = true;
    Promise.all([
      loadMaskPixels(result.assets.mask),
      loadMaskPixels(result.assets.uncertainty),
      loadMaskPixels(fire?.enabled ? result.assets.fire_mask : null)
    ]).then(([affected, uncertaintyMask, fireMask]) => {
      if (active) setMaskCache({ key: maskCacheKey, pixels: { affected, uncertainty: uncertaintyMask, fire: fireMask } });
    });
    return () => {
      active = false;
    };
  }, [maskCacheKey, result.assets.mask, result.assets.uncertainty, result.assets.fire_mask, fire?.enabled]);
  useEffect(() => {
    const viewport = imageViewportRef.current;
    if (!viewport) return undefined;
    const handleWheelZoom = event => {
      const deltaMultiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1;
      wheelDeltaRef.current += event.deltaY * deltaMultiplier;
      const direction = Math.sign(wheelDeltaRef.current);
      const currentZoom = zoomRef.current;
      const canZoom = (direction < 0 && currentZoom < 300) || (direction > 0 && currentZoom > 100);
      if (!canZoom) {
        wheelDeltaRef.current = 0;
        return;
      }
      event.preventDefault();
      const steps = Math.trunc(Math.abs(wheelDeltaRef.current) / 100);
      if (!steps) return;
      wheelDeltaRef.current -= direction * steps * 100;
      const previousZoom = currentZoom;
      const nextZoom = Math.min(300, Math.max(100, previousZoom - direction * steps * 25));
      if (nextZoom === previousZoom) return;
      const bounds = viewport.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      zoomRef.current = nextZoom;
      pendingZoomAnchorRef.current = {
        viewport,
        previousZoom,
        zoom: nextZoom,
        x,
        y,
        contentX: viewport.scrollLeft + x,
        contentY: viewport.scrollTop + y
      };
      setZoom(nextZoom);
    };
    viewport.addEventListener('wheel', handleWheelZoom, { passive: false });
    return () => viewport.removeEventListener('wheel', handleWheelZoom);
  }, []);
  const maskPixels = maskCache?.key === maskCacheKey ? maskCache.pixels : null;
  const visibleSteps = fire?.enabled ? [...steps, ...activeFireSteps] : steps;
  const downloads = [['overlay', 'Superposición de cicatriz JPG', 'jpg'], ['mask', 'Máscara binaria PNG', 'png'], ['labels', 'Etiquetas 0 / 1 / 255 PNG', 'png'], ['regions', 'Perímetros JSON', 'json'], ['metadata', 'Análisis y parámetros', 'json'], ['quality', 'Comprobaciones de calidad', 'json']];
  if (fire?.enabled) downloads.splice(1, 0, ['fire_overlay', 'Superposición de focos JPG', 'jpg'], ['fire_mask', 'Máscara de focos PNG', 'png'], ['active_labels', 'Etiquetas 0 / 1 / 2 / 255 PNG', 'png'], ['hotspots', 'Coordenadas de focos JSON', 'json']);
  function updateZoom(nextZoom) {
    const boundedZoom = Math.min(300, Math.max(100, nextZoom));
    zoomRef.current = boundedZoom;
    pendingZoomAnchorRef.current = null;
    setZoom(boundedZoom);
  }
  function handleMapPanStart(event) {
    if (event.button !== 0 || event.pointerType === 'touch') return;
    const viewport = imageViewportRef.current;
    if (!viewport) return;
    const bounds = viewport.getBoundingClientRect();
    if (event.target === viewport && (event.clientX > bounds.left + viewport.clientWidth || event.clientY > bounds.top + viewport.clientHeight)) return;
    event.preventDefault();
    setHoveredFeature(null);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop
    };
    setIsPanning(true);
    viewport.setPointerCapture(event.pointerId);
  }
  function handleMapPanMove(event) {
    const drag = dragRef.current;
    const viewport = imageViewportRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !viewport) return;
    viewport.scrollLeft = drag.scrollLeft - (event.clientX - drag.startX);
    viewport.scrollTop = drag.scrollTop - (event.clientY - drag.startY);
  }
  function handleMapPanEnd(event) {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setIsPanning(false);
  }
  function maskHasPixel(mask, xRatio, yRatio) {
    if (!mask) return false;
    const x = Math.min(mask.width - 1, Math.max(0, Math.floor(xRatio * mask.width)));
    const y = Math.min(mask.height - 1, Math.max(0, Math.floor(yRatio * mask.height)));
    return mask.pixels[y * mask.width + x] === 1;
  }
  function handleMapPointerMove(event) {
    const stack = imageStackRef.current;
    const bounds = stack?.getBoundingClientRect();
    if (!bounds?.width || !bounds?.height) return;
    const localX = Math.min(bounds.width, Math.max(0, event.clientX - bounds.left));
    const localY = Math.min(bounds.height, Math.max(0, event.clientY - bounds.top));
    const xRatio = localX / bounds.width;
    const yRatio = localY / bounds.height;
    const originalX = xRatio * result.original_size.width;
    const originalY = yRatio * result.original_size.height;
    const target = event.target?.closest?.('[data-map-feature]');
    const targetType = target?.getAttribute('data-map-feature');
    const targetRegionId = Number(target?.getAttribute('data-region-id')) || null;
    const hotspotId = Number(target?.getAttribute('data-hotspot-id')) || null;
    let type = null;
    if (targetType === 'perimeter' && perimeter) type = 'perimeter';
    else if (targetType === 'fire' && showFire && fire?.enabled) type = 'fire';
    else if (showFire && fire?.enabled && maskHasPixel(maskPixels?.fire, xRatio, yRatio)) type = 'fire';
    else if (uncertain && maskHasPixel(maskPixels?.uncertainty, xRatio, yRatio)) type = 'uncertainty';
    else if (segmentation && maskHasPixel(maskPixels?.affected, xRatio, yRatio)) type = 'affected';
    else if (targetType === 'affected' && segmentation) type = 'affected';
    if (!type) {
      setHoveredFeature(null);
      return;
    }
    const region = (targetRegionId && result.regions.find(item => item.id === targetRegionId)) || ((type === 'affected' || type === 'perimeter') ? regionAtPoint(result.regions, originalX, originalY) : null);
    const hotspot = type === 'fire' && ((hotspotId && fire?.hotspots?.find(item => item.id === hotspotId)) || fire?.hotspots?.find(item => {
      const [left, top, width, height] = item.bbox;
      return originalX >= left && originalX <= left + width && originalY >= top && originalY <= top + height;
    }));
    const featureRegion = type === 'affected' || type === 'perimeter' ? region : null;
    let label;
    let detail;
    if (type === 'perimeter') {
      label = featureRegion ? `Perímetro · Región ${featureRegion.id}` : 'Perímetro estimado';
      detail = `${number((featureRegion?.perimeter_m_estimated ?? result.stats.perimeter_m_estimated) / 1000)} km estimados`;
    } else if (type === 'affected') {
      label = featureRegion ? `Área posiblemente afectada · Región ${featureRegion.id}` : 'Área posiblemente afectada';
      detail = featureRegion
        ? `${number(featureRegion.area_hectares_estimated)} ha estimadas · ${number(featureRegion.perimeter_m_estimated / 1000)} km de perímetro`
        : `${number(result.stats.affected_area_hectares_estimated)} ha estimadas · ${number(result.stats.affected_percent)}% de la escena`;
    } else if (type === 'uncertainty') {
      label = 'Área de incertidumbre';
      detail = `${number(result.stats.uncertain_percent)}% de la escena · revisar por humo, nube o falta de datos`;
    } else {
      label = hotspot ? `Posible fuego activo · Foco ${hotspot.id}` : 'Posible fuego activo';
      detail = hotspot
        ? `${number(hotspot.area_hectares_estimated)} ha aprox. · ${number(hotspot.seed_pixels)} señales semilla`
        : `${number(fire.stats.active_area_hectares_estimated)} ha candidatas · ${number(fire.stats.hotspot_count)} focos`;
    }
    const tooltipWidth = Math.max(0, Math.min(240, bounds.width - 16));
    const left = localX + tooltipWidth + 24 < bounds.width ? localX + 12 : Math.max(8, localX - tooltipWidth - 12);
    const top = localY + 96 < bounds.height ? localY + 12 : Math.max(8, localY - 96);
    const next = { type, regionId: featureRegion?.id, hotspotId: type === 'fire' ? hotspot?.id : null, label, detail, left, top };
    setHoveredFeature(previous => previous?.type === next.type && previous.regionId === next.regionId && previous.hotspotId === next.hotspotId && Math.abs(previous.left - next.left) < 6 && Math.abs(previous.top - next.top) < 6 ? previous : next);
  }
  return <>
    <section className="result-heading" aria-labelledby="result-title">
      <div>
<span className="eyebrow">RESULTADO PARA {result.scene_name}</span>
<h2 id="result-title">Resumen de la escena</h2>
</div>
      <span className="result-badge" role="status" aria-live="polite">
<span />Análisis completado · {number(result.stats.processing_ms / 1000)} s</span>
    </section>
    <div className="stat-grid" role="group" aria-label="Resumen numérico del análisis">
      <div>
<span>Superficie detectada</span>
<strong>{number(result.stats.affected_area_hectares_estimated)}<small>ha</small>
</strong>
<p>{number(result.stats.affected_percent)}% del encuadre · estimación</p>
</div>
      <div>
<span>Regiones delimitadas</span>
<strong>{number(result.stats.region_count)}</strong>
<p>con evidencia de afectación</p>
</div>
      <div>
<span>Perímetro exterior</span>
<strong>{number(result.stats.perimeter_m_estimated / 1000)}<small>km</small>
</strong>
<p>estimado · {number(result.config.pixel_size_m)} m/píxel original</p>
</div>
      <div>
<span>{hasTrueColor ? 'Zona incierta' : 'Sin datos SWIR'}</span>
<strong>{number(result.stats.uncertain_percent)}<small>%</small>
</strong>
<p>{hasTrueColor ? 'humo, nube o falta de datos estimados' : 'píxeles sin datos en la composición'}</p>
</div>
    </div>
    <section className="viewer-card" role="region" aria-label="Visor del incendio">
      <div className="viewer-toolbar">
        <div className="segmented" role="group" aria-label="Composición de fondo">
{hasTrueColor && <button type="button" aria-pressed={base === 'true-color'} className={base === 'true-color' ? 'active' : ''} onClick={() => setBase('true-color')}>Color natural</button>}
<button type="button" aria-pressed={base === 'swir'} className={base === 'swir' ? 'active' : ''} onClick={() => setBase('swir')}>SWIR</button>
</div>
        <label className="zoom-label">Ampliación del visor <input aria-label="Ampliación del visor" aria-valuetext={`${zoom}%`} type="range" min="100" max="300" step="25" value={zoom} onChange={e => updateZoom(Number(e.target.value))} />
<span>{zoom}%</span>
</label>
      </div>
      <div ref={imageViewportRef} className={`image-scroll${isPanning ? ' is-panning' : ''}`} role="region" aria-label="Mapa analizado. Arrastra para desplazarte y usa la rueda del ratón para ampliar o reducir." tabIndex="0" onPointerDown={handleMapPanStart} onPointerMove={handleMapPanMove} onPointerUp={handleMapPanEnd} onPointerCancel={handleMapPanEnd} onLostPointerCapture={handleMapPanEnd} onDragStart={event => event.preventDefault()}>
        <div ref={imageStackRef} className={`image-stack${hoveredFeature ? ' map-feature-hovered' : ''}`} onPointerMove={handleMapPointerMove} onPointerLeave={() => setHoveredFeature(null)} style={{
          width: `${zoom}%`
        }}>
          <img className="base-image" src={result.assets[base]} alt={`Composición ${base === 'swir' ? 'SWIR' : 'en color natural'} de ${result.scene_name}`} />
          {segmentation && <img className="raster-layer" style={{
            opacity: opacity / 100
          }} src={result.assets.layers} alt="" />}
          {segmentation && <div className={`affected-pattern-layer ${hoveredFeature?.type === 'affected' ? 'is-highlighted' : ''}`} style={{
            opacity: opacity / 100,
            maskImage: `url(${result.assets.mask})`,
            WebkitMaskImage: `url(${result.assets.mask})`,
            WebkitMaskSize: '100% 100%',
            WebkitMaskRepeat: 'no-repeat'
          }} />}
          {uncertain && <div className={`uncertainty-layer ${hoveredFeature?.type === 'uncertainty' ? 'is-highlighted' : ''}`} style={{
            maskImage: `url(${result.assets.uncertainty})`,
            WebkitMaskImage: `url(${result.assets.uncertainty})`,
            WebkitMaskSize: '100% 100%',
            WebkitMaskRepeat: 'no-repeat'
          }} />}
          {fire?.enabled && showFire && <img className={`fire-raster-layer ${hoveredFeature?.type === 'fire' ? 'is-highlighted' : ''}`} src={result.assets.fire_layer} alt="" />}
          {fire?.enabled && showFire && <div className={`fire-pattern-layer ${hoveredFeature?.type === 'fire' ? 'is-highlighted' : ''}`} style={{
            maskImage: `url(${result.assets.fire_mask})`,
            WebkitMaskImage: `url(${result.assets.fire_mask})`,
            WebkitMaskSize: '100% 100%',
            WebkitMaskRepeat: 'no-repeat'
          }} />}
          {(segmentation || perimeter) && <Contours result={result} selected={selected} hoveredFeature={hoveredFeature} showAffected={segmentation} showPerimeter={perimeter} />}
          {fire?.enabled && showFire && <FireMarkers hotspots={fire.hotspots} originalSize={result.original_size} hoveredFeature={hoveredFeature} />}
          {hoveredFeature && <div className={`map-tooltip map-tooltip-${hoveredFeature.type}`} role="tooltip" aria-live="polite" style={{ left: hoveredFeature.left, top: hoveredFeature.top }}>
            <strong>{hoveredFeature.label}</strong>
            <span>{hoveredFeature.detail}</span>
          </div>}
        </div>
      </div>
      <div className="layer-toolbar" role="group" aria-label="Capas del resultado">
        <label>
<input type="checkbox" checked={segmentation} onChange={e => setSegmentation(e.target.checked)} />
<i className="legend-swatch affected-area" />Área posiblemente afectada</label>
        <label>
<input type="checkbox" checked={perimeter} onChange={e => setPerimeter(e.target.checked)} />
<i className="legend-line" />Perímetro</label>
        <label>
<input type="checkbox" checked={uncertain} onChange={e => setUncertain(e.target.checked)} />
<i className="legend-swatch uncertainty-swatch" />Área de incertidumbre</label>
        {fire?.enabled && <label className="fire-layer-toggle">
<input type="checkbox" checked={showFire} onChange={e => setShowFire(e.target.checked)} />
<i className="legend-swatch fire-red" />Posible fuego activo · {number(fire.stats.hotspot_count)}</label>}
        <label className="opacity-label">Opacidad <input aria-label="Opacidad del área posiblemente afectada" disabled={!segmentation} type="range" min="0" max="90" value={opacity} onChange={e => setOpacity(Number(e.target.value))} />
</label>
      </div>
      <div className="viewer-caption">
<span>{number(result.original_size.width)} × {number(result.original_size.height)} px originales</span>
<span>Máscara: {result.analysis_size.width} × {result.analysis_size.height} px · {number(result.config.pixel_size_m)} m/px original</span>
</div>
    </section>
    <div className="detail-grid">
      <section className="panel regions-panel" aria-labelledby="regions-title" style={{ height: exportContentHeight ? `${exportContentHeight + 42}px` : undefined }}>
<div className="section-title">
<h3 id="regions-title">Regiones detectadas</h3>
<span>{result.regions.length}</span>
</div>
        {result.regions.length ? <ul className="region-list" aria-label="Regiones delimitadas">{result.regions.map(region => <li className="region-item" key={region.id}><button type="button" aria-pressed={selected === region.id} className={`region-row ${selected === region.id ? 'selected' : ''} ${hoveredFeature?.regionId === region.id ? 'map-hovered' : ''}`} onClick={() => setSelected(selected === region.id ? null : region.id)}>
<span className="region-number">{String(region.id).padStart(2, '0')}</span>
<span>
<strong>Región {region.id}</strong>
<small>{number(region.area_hectares_estimated)} ha estimadas</small>
</span>
<span>{number(region.perimeter_m_estimated / 1000)} km</span>
</button></li>)}</ul> : <p className="muted">No se han encontrado regiones con estos parámetros. Puedes revisar la evidencia y ajustar la sensibilidad.</p>}
      </section>
      <section className="panel export-panel" aria-labelledby="export-title">
<div className="export-panel-content" ref={exportPanelContentRef}>
<span className="eyebrow">DATOS PARA SEGUIR TRABAJANDO</span>
<h3 id="export-title">Descargar resultados</h3>
<p>Guarda las máscaras, los perímetros y el resumen de este análisis.</p>
<div className="downloads">{downloads.map(([key, label, extension]) => <a key={key} href={result.assets[key]} download={`brasa-${key}.${extension}`}>{label}<span aria-hidden="true">↗</span>
</a>)}</div>
<p className="unit-note">Escala declarada de {number(result.config.pixel_size_m)} m por píxel original cuadrado. El cálculo compensa la reducción de resolución. Son estimaciones sin georreferenciación.</p>
</div>
</section>
    </div>
    <section className="panel process-panel" aria-labelledby="process-title">
<div className="section-title">
<div>
<span className="eyebrow">UN PROCESO EXPLICABLE</span>
<h3 id="process-title">{fire?.enabled ? 'Del territorio a los focos activos' : 'De la imagen al perímetro'}</h3>
</div>
<span>{visibleSteps.length} pasos</span>
</div>
<div className={`step-list ${fire?.enabled ? 'advanced' : ''}`} role="group" aria-label="Pasos del análisis">{visibleSteps.map(([key, index, title]) => <button type="button" key={key} aria-pressed={activeStep === key} className={`step-card ${activeStep === key ? 'selected' : ''}`} onClick={() => setActiveStep(key)}>
<img src={result.assets[key]} alt="" loading="lazy" />
<span>{index}</span>
<strong>{title}</strong>
</button>)}</div>
<div className="step-detail">
<img src={result.assets[activeStep]} alt={visibleSteps.find(([key]) => key === activeStep)[2]} loading="lazy" />
<p>{visibleSteps.find(([key]) => key === activeStep)[3]}</p>
</div>
</section>
    {fire?.enabled && <section className="panel active-fire-summary" aria-labelledby="active-fire-title">
<div className="section-title">
<div><span className="eyebrow">SEÑALES EN EL MOMENTO DE LA CAPTURA</span><h3 id="active-fire-title">Posibles focos activos</h3></div>
<span>{number(fire.stats.hotspot_count)} regiones</span>
</div>
<p>{number(fire.stats.active_pixels)} píxeles candidatos agrupados en focos. Los marcadores rojos identifican posibles focos; el área afectada aparece en azul.</p>
{fire.hotspots.length > 0 ? <div className="hotspot-list">{fire.hotspots.slice(0, 12).map(hotspot => <div className="hotspot-row" key={hotspot.id}>
<strong>Foco {String(hotspot.id).padStart(2, '0')}</strong>
<span>x {number(hotspot.centroid[0])} · y {number(hotspot.centroid[1])} px</span>
<span>{number(hotspot.area_hectares_estimated)} ha aprox. · {number(hotspot.seed_pixels)} semillas</span>
</div>)}</div> : <p className="muted">No se encontraron píxeles candidatos con estos umbrales. Esto no demuestra que no hubiera fuego activo.</p>}
{fire.warnings.length > 0 && <ul>{fire.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>}
</section>}
    {result.quality && <section className="panel quality-panel" aria-labelledby="quality-title">
<div className="section-title"><h3 id="quality-title">Comprobaciones automáticas</h3>{result.quality.status !== 'usable' && <span>Revisar resultado</span>}</div>
<p>Comprueban la entrada y las condiciones de observación. La precisión de detección requiere máscaras de referencia independientes.</p>
<div className="quality-checks">{result.quality.checks.map(check => <div className={`quality-check ${check.status}`} key={check.id}><strong>{check.status === 'ok' ? '✓' : '△'} {check.label}</strong><p>{check.detail}</p></div>)}</div>
</section>}
    <details className="method-notes">
<summary>Alcance del método y parámetros utilizados</summary>
<ul>{result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
<p>Algoritmo: {result.algorithm}. Sensibilidad: {result.config.sensitivity}. Umbral de semillas: {(0.64 + (0.5 - result.config.sensitivity) * 0.24).toFixed(2)}. Resolución inicial: {result.coarse_size.width} × {result.coarse_size.height}. Refinamiento: {result.config.refine ? 'activado' : 'desactivado'}. La puntuación de color no expresa una probabilidad calibrada ni una validación independiente.</p>
</details>
  </>;
}
export default function ImageForm() {
  const [scenes, setScenes] = useState([]);
  const [sceneId, setSceneId] = useState('niebla');
  const [mode, setMode] = useState('scenes');
  const [uploadMode, setUploadMode] = useState('paired');
  const [trueFile, setTrueFile] = useState(null);
  const [swirFile, setSwirFile] = useState(null);
  const [uploadPreviewUrls, setUploadPreviewUrls] = useState({ trueColor: null, swir: null });
  const [previewSlide, setPreviewSlide] = useState(0);
  const [previewDragActive, setPreviewDragActive] = useState(false);
  const [sensitivity, setSensitivity] = useState(50);
  const [resolution, setResolution] = useState(1536);
  const [refine, setRefine] = useState(true);
  const [pixelSize, setPixelSize] = useState(20);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const [accessibilityOpen, setAccessibilityOpen] = useState(false);
  const accessibilityMenuRef = useRef(null);
  const accessibilityButtonRef = useRef(null);
  const [accessibility, setAccessibility] = useState(loadAccessibilitySettings);
  useEffect(() => {
    const previews = {
      trueColor: trueFile ? URL.createObjectURL(trueFile) : null,
      swir: swirFile ? URL.createObjectURL(swirFile) : null
    };
    setUploadPreviewUrls(previews);
    return () => Object.values(previews).forEach(url => url && URL.revokeObjectURL(url));
  }, [trueFile, swirFile]);
  useEffect(() => {
    try {
      window.localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify(accessibility));
    } catch {
      // La página sigue siendo utilizable aunque el navegador no permita guardar preferencias.
    }
  }, [accessibility]);
  useEffect(() => {
    if (!accessibilityOpen) return;
    const closeFromOutside = event => {
      if (!accessibilityMenuRef.current?.contains(event.target)) setAccessibilityOpen(false);
    };
    const closeFromKeyboard = event => {
      if (event.key === 'Escape') {
        setAccessibilityOpen(false);
        accessibilityButtonRef.current?.focus();
      }
    };
    const closeFromFocus = event => {
      if (!accessibilityMenuRef.current?.contains(event.target)) setAccessibilityOpen(false);
    };
    document.addEventListener('pointerdown', closeFromOutside);
    document.addEventListener('keydown', closeFromKeyboard);
    document.addEventListener('focusin', closeFromFocus);
    return () => {
      document.removeEventListener('pointerdown', closeFromOutside);
      document.removeEventListener('keydown', closeFromKeyboard);
      document.removeEventListener('focusin', closeFromFocus);
    };
  }, [accessibilityOpen]);
  useEffect(() => {
    const controller = new AbortController();
    request('/api/scenes', {
      signal: controller.signal
    }).then(data => {
      setScenes(data);
      setConnected(true);
      if (data.length) setSceneId(data[0].id);
    }).catch(err => {
      if (err.name !== 'AbortError') setError('No se puede conectar con FastAPI. Comprueba que el backend esté iniciado.');
    });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => setElapsed(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);
  async function submit(event) {
    event.preventDefault();
    if (mode === 'uploads' && (!swirFile || uploadMode === 'paired' && !trueFile)) {
      setError(uploadMode === 'swir_only' ? 'Selecciona una composición SWIR.' : 'Selecciona True Color y SWIR, o cambia el modo a Solo SWIR.');
      document.getElementById(!swirFile ? 'swir-file' : 'true-color-file')?.focus();
      return;
    }
    setBusy(true);
    setElapsed(0);
    setError('');
    setResult(null);
    try {
      let data;
      if (mode === 'scenes') data = await request(`/api/scenes/${sceneId}/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          sensitivity: sensitivity / 100,
          max_side: resolution,
          refine,
          pixel_size_m: pixelSize,
          active_fire: true
        })
      });else {
        const form = new FormData();
        if (uploadMode === 'paired') form.append('image1', trueFile);
        form.append('image2', swirFile);
        form.append('input_mode', uploadMode);
        form.append('sensitivity', sensitivity / 100);
        form.append('max_side', resolution);
        form.append('refine', refine);
        form.append('pixel_size_m', pixelSize);
        form.append('active_fire', 'true');
        data = await request('/api/process', {
          method: 'POST',
          body: form
        });
      }
      setResult(data);
      setConnected(true);
    } catch (err) {
      setError(err.message || 'No se pudo completar el análisis.');
    } finally {
      setBusy(false);
    }
  }
  function handleUploadFile(composition, file) {
    if (!file) return;
    const supportedType = ['image/jpeg', 'image/png', 'image/webp'].includes(file.type);
    const supportedExtension = /\.(jpe?g|png|webp)$/i.test(file.name);
    if (!supportedType && !supportedExtension) {
      setError('El archivo debe ser una imagen JPEG, PNG o WebP.');
      return false;
    }
    if (file.size > 80 * 1024 * 1024) {
      setError('La imagen no puede superar los 80 MB.');
      return false;
    }
    (composition === 'trueColor' ? setTrueFile : setSwirFile)(file);
    setPreviewSlide(composition === 'trueColor' ? 0 : 1);
    setResult(null);
    setError('');
    return true;
  }
  function removeUploadFile(composition) {
    (composition === 'trueColor' ? setTrueFile : setSwirFile)(null);
    setPreviewSlide(composition === 'trueColor' ? 0 : 1);
    setResult(null);
    setError('');
  }
  function handlePreviewDragEnter(event) {
    if (mode !== 'uploads' || !Array.from(event.dataTransfer?.types || []).includes('Files')) return;
    event.preventDefault();
    setPreviewDragActive(true);
  }
  function handlePreviewDragOver(event) {
    if (mode !== 'uploads' || !Array.from(event.dataTransfer?.types || []).includes('Files')) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    setPreviewDragActive(true);
  }
  function handlePreviewDragLeave(event) {
    if (!event.currentTarget.contains(event.relatedTarget)) setPreviewDragActive(false);
  }
  function handlePreviewDrop(event) {
    if (mode !== 'uploads' || !event.dataTransfer?.files?.length) return;
    event.preventDefault();
    setPreviewDragActive(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length > (uploadMode === 'paired' ? 2 : 1)) {
      setError(uploadMode === 'swir_only' ? 'Arrastra una composición SWIR.' : 'Arrastra como máximo dos imágenes: una True Color y una SWIR.');
      return;
    }
    const compositions = uploadMode === 'swir_only' ? ['swir'] : previewSlide === 0 ? ['trueColor', 'swir'] : ['swir', 'trueColor'];
    let rejectedFile = false;
    files.forEach((file, index) => {
      if (!handleUploadFile(compositions[index], file)) rejectedFile = true;
    });
    if (rejectedFile) setError('Una o más imágenes no son válidas. Usa JPEG, PNG o WebP de hasta 80 MB.');
  }
  function changeInput(action, nextSlide = 0) {
    action();
    setPreviewSlide(nextSlide);
    setResult(null);
    setError('');
  }
  const selectedScene = scenes.find(scene => scene.id === sceneId);
  const previewComposition = mode === 'uploads' && uploadMode === 'swir_only' ? 'SWIR' : previewSlide === 0 ? 'True Color' : 'SWIR';
  const previewFile = mode === 'uploads' && uploadMode === 'swir_only' ? swirFile : previewSlide === 0 ? trueFile : swirFile;
  const previewImage = mode === 'scenes'
    ? selectedScene ? (previewSlide === 0 ? selectedScene.thumbnail_url : `/api/scenes/${selectedScene.id}/preview/swir`) : null
    : uploadMode === 'swir_only' ? uploadPreviewUrls.swir : previewSlide === 0 ? uploadPreviewUrls.trueColor : uploadPreviewUrls.swir;
  const hasPreviewSource = mode === 'uploads' || Boolean(selectedScene);
  const canChangePreview = hasPreviewSource && !(mode === 'uploads' && uploadMode === 'swir_only');
  const previewAlt = mode === 'scenes'
    ? `Composición ${previewComposition} de la escena ${selectedScene?.name || ''}`
    : `Vista previa de la composición ${previewComposition}${previewFile?.name ? `: ${previewFile.name}` : ''}`;
  const previewSourceName = mode === 'scenes'
    ? selectedScene?.name || 'sin escena seleccionada'
    : previewFile?.name || 'sin archivo cargado';
  const placeholderDescription = mode === 'uploads'
    ? uploadMode === 'swir_only' ? 'Arrastra aquí una composición SWIR o selecciónala para verla en pantalla completa.' : `Arrastra aquí una imagen ${previewComposition} o selecciónala para verla en pantalla completa. También puedes soltar ambas composiciones a la vez.`
    : connected ? 'Elige una escena en el panel de selección para ver sus composiciones.' : 'Las escenas se mostrarán aquí cuando termine la conexión.';
  const textScale = accessibility.fontSize / 100;
  const accessibilityClasses = `theme-${accessibility.theme} font-${accessibility.fontFamily}${accessibility.highContrast ? ' high-contrast' : ''}`;
  const scaledFontSizes = Object.fromEntries(
    [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 20, 23, 27, 28, 29, 30, 34, 39]
      .map(size => [`--font-size-${size}`, `${size * textScale}px`])
  );
  const accessibilityStyles = {
    ...scaledFontSizes,
    '--font-small': `${12 * textScale}px`,
    '--font-body': `${12 * textScale}px`,
    '--font-sidebar-heading': `${29 * textScale}px`,
    '--font-sidebar-heading-mobile': `${27 * textScale}px`,
    '--font-welcome-heading': `clamp(${34 * textScale}px, ${3.7 * textScale}vw, ${58 * textScale}px)`,
    '--font-welcome-heading-mobile': `${39 * textScale}px`,
    '--font-result-heading': `${34 * textScale}px`,
    '--font-result-heading-mobile': `${30 * textScale}px`,
    '--font-section-heading': `${13 * textScale}px`,
    '--font-popover-heading': `${26 * textScale}px`,
    '--font-setting-heading': `${13 * textScale}px`,
    '--font-setting-hint': `${11 * textScale}px`
  };
  return <div className={`app-shell ${accessibilityClasses}`} style={accessibilityStyles}>
    <a className="skip-link" href="#main-content">Saltar al contenido principal</a>
    <header className="topbar">
<a className="brand" href="/" aria-label="Indra Group, inicio">
<img className="brand-mark brand-mark-on-light" src={indraLogoLightTheme} alt="" />
<img className="brand-mark brand-mark-on-dark" src={indraLogoDarkTheme} alt="" />
</a>
<div className="topbar-title">INDRA ESPACIO <span>/</span> OBSERVACIÓN SATELITAL</div>
<div className="topbar-actions">
<div className="accessibility-control" ref={accessibilityMenuRef}>
<button ref={accessibilityButtonRef} className="accessibility-trigger" type="button" aria-label="Abrir opciones de accesibilidad" aria-haspopup="dialog" aria-expanded={accessibilityOpen} aria-controls={accessibilityOpen ? 'accessibility-panel' : undefined} onClick={() => setAccessibilityOpen(open => !open)}>
<svg aria-hidden="true" viewBox="0 -960 960 960" fill="currentColor"><path d="M423.5-743.5Q400-767 400-800t23.5-56.5Q447-880 480-880t56.5 23.5Q560-833 560-800t-23.5 56.5Q513-720 480-720t-56.5-23.5ZM360-80v-520q-60-5-122-15t-118-25l20-80q78 21 166 30.5t174 9.5q86 0 174-9.5T820-720l20 80q-56 15-118 25t-122 15v520h-80v-240h-80v240h-80Z" /></svg>
<span>Accesibilidad</span>
</button>
{accessibilityOpen && <div className="accessibility-popover" id="accessibility-panel" role="dialog" aria-labelledby="accessibility-title">
<div className="accessibility-popover-heading">
<div><span className="eyebrow">PERSONALIZA TU EXPERIENCIA</span><h2 id="accessibility-title">Accesibilidad</h2></div>
<button className="accessibility-close" type="button" aria-label="Cerrar opciones de accesibilidad" onClick={() => { setAccessibilityOpen(false); accessibilityButtonRef.current?.focus(); }}>×</button>
</div>
<label className="accessibility-setting" htmlFor="accessibility-font-size">
<span className="accessibility-setting-title"><span>Tamaño del texto</span><output aria-hidden="true" htmlFor="accessibility-font-size">{accessibility.fontSize}%</output></span>
<input id="accessibility-font-size" className="accessibility-range" type="range" min="100" max="160" step="10" value={accessibility.fontSize} aria-valuetext={`${accessibility.fontSize}%`} onChange={event => setAccessibility(value => ({ ...value, fontSize: Number(event.target.value) }))} />
<span className="range-endpoints" aria-hidden="true"><span>A</span><span className="large-a">A</span></span>
</label>
<label className="accessibility-setting" htmlFor="accessibility-font-family">
<span className="accessibility-setting-title"><span>Tipo de letra</span><span className="setting-hint">Elige la que te resulte más cómoda</span></span>
<select id="accessibility-font-family" value={accessibility.fontFamily} onChange={event => setAccessibility(value => ({ ...value, fontFamily: event.target.value }))}>
<option value="indra">Neo Sans · Indra</option>
<option value="arial">Arial</option>
<option value="verdana">Verdana</option>
<option value="georgia">Georgia</option>
<option value="opendyslexic">OpenDyslexic · lectura accesible</option>
</select>
</label>
<div className="accessibility-setting theme-setting">
<span className="accessibility-setting-title"><span>Tema de pantalla</span><span className="setting-hint">{accessibility.theme === 'dark' ? 'Modo oscuro' : 'Modo claro'}</span></span>
<div className="theme-choice">
<span aria-hidden="true">☀</span>
<button className="theme-switch" type="button" role="switch" aria-checked={accessibility.theme === 'dark'} aria-label="Tema oscuro" onClick={() => setAccessibility(value => ({ ...value, theme: value.theme === 'dark' ? 'light' : 'dark' }))}><span /></button>
<span aria-hidden="true">☾</span>
</div>
</div>
<div className="accessibility-setting theme-setting">
<span className="accessibility-setting-title"><span>Contraste de pantalla</span><span className="setting-hint">{accessibility.highContrast ? 'Alto contraste' : 'Contraste normal'}</span></span>
<div className="theme-choice contrast-choice">
<span className="contrast-mark" aria-hidden="true">A</span>
<button className="theme-switch contrast-switch" type="button" role="switch" aria-checked={accessibility.highContrast} aria-label="Alto contraste" onClick={() => setAccessibility(value => ({ ...value, highContrast: !value.highContrast }))}><span /></button>
<strong className="contrast-mark high" aria-hidden="true">A</strong>
</div>
</div>
</div>}
</div>
</div>
</header>
    <aside className="sidebar" aria-label="Selección y parámetros del análisis">
<div className="sidebar-intro">
<span className="eyebrow">ANÁLISIS DE INCENDIOS</span>
<h1 className="visually-hidden">Análisis de incendios forestales</h1>
<p>Consulta el área posiblemente afectada, su perímetro y las señales compatibles con actividad de fuego.</p>
</div>
      <form id="analysis-form" onSubmit={submit}>
<fieldset disabled={busy}>
<legend className="visually-hidden">Imágenes y parámetros del análisis</legend>
<div className="segmented source-tabs" role="group" aria-label="Origen de las imágenes">
<button type="button" aria-pressed={mode === 'scenes'} className={mode === 'scenes' ? 'active' : ''} onClick={() => changeInput(() => setMode('scenes'))}>Escenas disponibles</button>
<button type="button" aria-pressed={mode === 'uploads'} className={mode === 'uploads' ? 'active' : ''} onClick={() => changeInput(() => setMode('uploads'))}>Subir imágenes</button>
</div>
        {mode === 'scenes' ? <div className="scene-list" role="group" aria-label="Escenas disponibles">{scenes.map(scene => <button type="button" key={scene.id} className={`scene-card ${sceneId === scene.id ? 'selected' : ''}`} aria-label={`Seleccionar escena ${scene.name}, con imágenes True Color y SWIR`} aria-pressed={sceneId === scene.id} onClick={() => changeInput(() => setSceneId(scene.id))}>
<img src={scene.thumbnail_url} alt="" />
<span>
<strong>{scene.name}</strong>
<small>True Color + SWIR</small>
</span>
<i aria-hidden="true">{sceneId === scene.id ? '●' : '○'}</i>
</button>)}{!scenes.length && <p className="muted">Las escenas aparecerán al conectar con el backend.</p>}</div> : <div className="upload-list">
<div className="segmented source-tabs" role="group" aria-label="Modo de carga">
<button type="button" aria-pressed={uploadMode === 'paired'} className={uploadMode === 'paired' ? 'active' : ''} onClick={() => changeInput(() => setUploadMode('paired'))}>True Color + SWIR</button>
<button type="button" aria-pressed={uploadMode === 'swir_only'} className={uploadMode === 'swir_only' ? 'active' : ''} onClick={() => changeInput(() => { setUploadMode('swir_only'); setTrueFile(null); }, 1)}>Solo SWIR</button>
</div>
{(uploadMode === 'paired' ? [['True Color', 'trueColor', trueFile]] : []).concat([['Composición SWIR', 'swir', swirFile]]).map(([label, composition, file]) => <div className={`upload-field ${file ? 'has-file' : ''}`} key={label}>
<div className="upload-field-heading">
<label className="upload-field-title" htmlFor={`${composition === 'trueColor' ? 'true-color' : 'swir'}-file`}>{label}</label>
{file && <button className="upload-remove-button" type="button" aria-label={`Eliminar imagen ${label}: ${file.name}`} onClick={() => removeUploadFile(composition)}>
<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16M10 11v6m4-6v6M5 7l1 14h12l1-14M9 7V4h6v3" /></svg>
</button>}
</div>
<small id={`${composition === 'trueColor' ? 'true-color' : 'swir'}-file-help`} role="status" aria-live="polite">{file ? `Archivo seleccionado: ${file.name}` : 'Ningún archivo seleccionado · JPEG, PNG o WebP · hasta 80 MB'}</small>
<label className="upload-select-button" htmlFor={`${composition === 'trueColor' ? 'true-color' : 'swir'}-file`}>{file ? 'Cambiar imagen' : 'Seleccionar imagen'}</label>
<input className="visually-hidden upload-native-input" id={`${composition === 'trueColor' ? 'true-color' : 'swir'}-file`} type="file" accept="image/jpeg,image/png,image/webp" aria-label={label} aria-required="true" aria-describedby={`${composition === 'trueColor' ? 'true-color' : 'swir'}-file-help`} onChange={event => { handleUploadFile(composition, event.currentTarget.files[0]); event.currentTarget.value = ''; }} />
</div>)}<p className="muted">{uploadMode === 'paired' ? 'Usa True Color y SWIR de la misma escena, encuadre y momento de captura.' : 'Se analizará únicamente la composición SWIR. No se aplicarán los filtros que necesitan True Color.'}</p>
</div>}
        <div className="analysis-settings">
<div className="setting-title level-title">
<h2>Qué se va a mostrar</h2>
<span>CAPAS SEPARADAS</span>
</div>
<p className="analysis-hint">El análisis estima el área afectada y señala posibles focos. Podrás revisar cada resultado por separado.</p>
<div className="setting-title">
<h2>Ajustes de imagen</h2>
<span>OPCIONAL</span>
</div>
<label className="slider-label" htmlFor="sensitivity">Sensibilidad de detección <strong>{sensitivity}%</strong>
</label>
<input id="sensitivity" className="wide-range" type="range" min="0" max="100" value={sensitivity} aria-valuetext={`${sensitivity}% de sensibilidad`} aria-describedby="sensitivity-range-help" onChange={e => setSensitivity(Number(e.target.value))} />
<div className="range-labels">
<span>Menos resultados</span>
<span>Más resultados</span>
</div>
<span id="sensitivity-range-help" className="visually-hidden">Un valor bajo prioriza menos resultados; un valor alto muestra más resultados candidatos.</span>
<label className="select-label" htmlFor="resolution">Nivel de detalle<select id="resolution" value={resolution} onChange={e => setResolution(Number(e.target.value))}>
<option value="1024">1024 px · rápida</option>
<option value="1536">1536 px · equilibrada</option>
<option value="2048">2048 px · detallada</option>
</select>
</label>
<label className="select-label" htmlFor="pixel-size">Tamaño del píxel original en metros<input id="pixel-size" aria-describedby="pixel-size-help" type="number" min="0.01" max="10000" step="any" required value={pixelSize} onChange={e => setPixelSize(e.target.value === '' ? '' : Number(e.target.value))} /></label>
<p className="analysis-hint" id="pixel-size-help">Sentinel-2 suele ofrecer 20 m por píxel en SWIR. Ajusta el valor si la imagen se ha remuestreado.</p>
<label className="refine-option">
<input type="checkbox" checked={refine} onChange={e => setRefine(e.target.checked)} />
<span>Mejorar el contorno<small>Ajusta los límites con más detalle</small>
</span>
</label>
</div>
</fieldset>
</form>
<button className="analyze-button sidebar-analyze-button" type="submit" form="analysis-form" aria-describedby="sidebar-analysis-form-help" disabled={busy || mode === 'scenes' && !scenes.length}>
{busy ? <><span className="spinner" aria-hidden="true" />Analizando escena · {elapsed} s</> : <>Analizar escena<span aria-hidden="true">↗</span></>}
</button>
<span id="sidebar-analysis-form-help" className="visually-hidden">Ejecuta el análisis con la escena seleccionada o con las imágenes True Color y SWIR cargadas.</span>
<div className="sidebar-foot">
<span className="tiny-mark" aria-hidden="true">◉</span>
<p>Indra Espacio · Observación satelital<br />Información para evaluar incendios forestales</p>
</div>
    </aside>
    <main className="main-content" id="main-content" tabIndex="-1">{error && <div className="error-banner" role="alert">{error}</div>}{busy && <div className="progress-banner" role="status" aria-live="polite">
<span className="spinner" aria-hidden="true" />Estamos analizando la escena. El resultado aparecerá aquí.</div>}
      {result ? <ResultViewer key={result.result_id} result={result} /> : <section className="welcome">
<div className="welcome-top">
<span className="eyebrow">OBSERVACIÓN SATELITAL</span>
<span className="edition">ANÁLISIS DE ESCENA</span>
</div>
<div className="welcome-heading-row">
<h2>Comprender el alcance.<br />
<em>Revisar cada señal.</em>
</h2>
<button className="analyze-button" type="submit" form="analysis-form" aria-describedby="analysis-form-help" disabled={busy || mode === 'scenes' && !scenes.length}>
{busy ? <><span className="spinner" aria-hidden="true" />Analizando escena · {elapsed} s</> : <>Analizar escena<span aria-hidden="true">↗</span></>}
</button>
<span id="analysis-form-help" className="visually-hidden">Ejecuta el análisis con la escena seleccionada o con las imágenes True Color y SWIR cargadas.</span>
</div>
<p>Elige una escena o sube tus imágenes. Consulta el perímetro estimado, las posibles señales de fuego activo y las zonas que requieren revisión.</p>
<div className={`welcome-image ${previewImage ? 'has-preview' : 'is-empty'}${mode === 'uploads' && !previewImage ? ' upload-empty' : ''}${previewDragActive ? ' drag-active' : ''}`} role="group" aria-roledescription="carrusel" aria-label={`Previsualización de las composiciones de ${mode === 'scenes' ? selectedScene?.name || 'la escena seleccionada' : 'tus imágenes'}`} onDragEnter={handlePreviewDragEnter} onDragOver={handlePreviewDragOver} onDragLeave={handlePreviewDragLeave} onDrop={handlePreviewDrop}>
{previewImage ? <img id="welcome-preview-image" key={previewImage} src={previewImage} alt={previewAlt} /> : <div className="upload-placeholder">
<svg aria-hidden="true" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="5" y="8" width="38" height="32" rx="4" /><circle cx="17" cy="19" r="3" /><path d="m8 35 11-10 7 7 6-6 8 9" /></svg>
<strong>Tu vista previa de {previewComposition} aparecerá aquí</strong>
<span>{placeholderDescription}</span>
{mode === 'uploads' && <label className="preview-file-picker">
<span>Seleccionar imagen {previewComposition}</span>
<input className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" aria-label={`Seleccionar imagen ${previewComposition}`} aria-describedby="preview-upload-guidance" onChange={event => { handleUploadFile(previewSlide === 0 ? 'trueColor' : 'swir', event.currentTarget.files[0]); event.currentTarget.value = ''; }} />
</label>}
</div>}
{mode === 'uploads' && previewImage && <>
<span className="preview-drop-hint" aria-hidden="true">Arrastra aquí para reemplazar la imagen</span>
<label className="preview-file-picker preview-file-picker-overlay">
<span>Cambiar imagen {previewComposition}</span>
<input className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" aria-label={`Cambiar imagen ${previewComposition}`} aria-describedby="preview-upload-guidance" onChange={event => { handleUploadFile(previewSlide === 0 ? 'trueColor' : 'swir', event.currentTarget.files[0]); event.currentTarget.value = ''; }} />
</label>
</>}
{mode === 'uploads' && <span id="preview-upload-guidance" className="visually-hidden">Arrastra una imagen JPEG, PNG o WebP hasta la vista previa, o selecciónala. Tamaño máximo: 80 MB. La imagen se asignará a la composición {previewComposition}. Si arrastras dos, la segunda se asignará a {previewSlide === 0 ? 'SWIR' : 'True Color'}.</span>}
{previewDragActive && <span className="preview-drop-feedback" role="status" aria-live="polite">Suelta la imagen {previewComposition} aquí</span>}
{canChangePreview && <div className="carousel-navigation" role="group" aria-label="Cambiar composición de la vista previa">
<button type="button" className="carousel-arrow" aria-label={`Mostrar composición anterior: ${previewSlide === 0 ? 'SWIR' : 'True Color'}`} onClick={() => setPreviewSlide(current => current === 0 ? 1 : 0)}><span aria-hidden="true">‹</span></button>
<button type="button" className="carousel-arrow" aria-label={`Mostrar composición siguiente: ${previewSlide === 0 ? 'SWIR' : 'True Color'}`} onClick={() => setPreviewSlide(current => current === 0 ? 1 : 0)}><span aria-hidden="true">›</span></button>
</div>}
<div className="carousel-status" role="status" aria-live="polite" aria-atomic="true">Vista {mode === 'uploads' && uploadMode === 'swir_only' ? 1 : previewSlide + 1} de {mode === 'uploads' && uploadMode === 'swir_only' ? 1 : 2} · {previewComposition}<span className="visually-hidden"> · {previewSourceName}</span></div>
<div className="image-label">
<span className="live-dot" aria-hidden="true" />{mode === 'scenes' ? selectedScene?.name || 'Escenas disponibles' : 'Tus composiciones satelitales'}<small>{previewComposition.toUpperCase()}</small>
</div>
</div>
<div className="welcome-features">
<div>
<span>01</span>
<strong>Localizar</strong>
<p>Revisa las señales de posible afectación.</p>
</div>
<div>
<span>02</span>
<strong>Delimitar</strong>
<p>Explora el perímetro y las regiones estimadas.</p>
</div>
<div>
<span>03</span>
<strong>Revisar</strong>
<p>Consulta la incertidumbre y descarga los resultados.</p>
</div>
</div>
<p className="welcome-note">Las superficies y perímetros son estimaciones basadas en la escala indicada. Las composiciones visuales no contienen valores de reflectancia originales.</p>
</section>}
      <footer className="main-footer">
<span>INDRA ESPACIO / OBSERVACIÓN SATELITAL</span>
<span>Una lectura clara para valorar el alcance del incendio.</span>
</footer>
    </main>
  </div>;
}
