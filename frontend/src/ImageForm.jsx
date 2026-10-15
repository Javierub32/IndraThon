import { useEffect, useRef, useState } from 'react';
const ACCESSIBILITY_STORAGE_KEY = 'brasa.accessibility';
const DEFAULT_ACCESSIBILITY = {
  fontSize: 100,
  fontFamily: 'indra',
  theme: 'light'
};
const ACCESSIBLE_FONTS = ['indra', 'arial', 'verdana', 'georgia'];
const number = value => new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 1
}).format(value);
const steps = [['swir', '01', 'Composición SWIR', 'Imagen de entrada utilizada para localizar señales de afectación.'], ['score', '02', 'Señales de color', 'Azul: evidencia baja. Amarillo: evidencia alta. Es una puntuación, no una probabilidad.'], ['seeds', '03', 'Zonas de referencia', 'Píxeles con señales visuales más claras.'], ['candidates', '04', 'Áreas candidatas', 'Superficies compatibles con las señales del análisis.'], ['grown', '05', 'Áreas conectadas', 'Candidatos próximos a zonas con señales claras.'], ['cleaned', '06', 'Límites depurados', 'Eliminación de ruido y relleno limitado de huecos.'], ['overlay', '07', 'Perímetro estimado', 'Resultado tras el ajuste opcional de los límites.']];
const activeFireSteps = [['fire_score', '08', 'Contraste de la imagen', 'Brillo y contraste del render. La equivalencia con bandas espectrales depende de la composición; no indica temperatura.'], ['fire_raw_seeds', '09', 'Primeras señales', 'Primer filtro de brillo y relación entre canales.'], ['fire_context', '10', 'Comparación del entorno', 'Compara las señales con el brillo de las zonas vecinas.'], ['fire_seeds', '11', 'Señales consistentes', 'Zonas candidatas con apoyo del entorno.'], ['fire_candidates', '12', 'Áreas candidatas', 'Píxeles compatibles con las señales detectadas.'], ['fire_grown', '13', 'Áreas agrupadas', 'Agrupación limitada de zonas próximas.'], ['fire_mask', '14', 'Posibles focos', 'Zonas con señales compatibles con actividad de fuego.']];
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
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
      theme: saved.theme === 'dark' ? 'dark' : DEFAULT_ACCESSIBILITY.theme
    };
  } catch {
    return DEFAULT_ACCESSIBILITY;
  }
}
function Contours({
  result,
  selected
}) {
  const {
    width,
    height
  } = result.original_size;
  return <svg className="contour-layer" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    {result.regions.map(region => {
      const rings = [region.outer, ...region.holes];
      const path = rings.map(ring => `M${ring.map(p => p.join(',')).join('L')}Z`).join(' ');
      return <path key={region.id} d={path} fill="none" stroke={selected === region.id ? '#FFFFFF' : '#FFBB21'} strokeWidth={selected === region.id ? 3 : 1.5} vectorEffect="non-scaling-stroke" />;
    })}
  </svg>;
}
function FireMarkers({
  hotspots,
  originalSize
}) {
  return <svg className="fire-markers-layer" viewBox={`0 0 ${originalSize.width} ${originalSize.height}`} aria-label="Marcadores de posibles focos activos">
    {hotspots.map(hotspot => {
      const [x, y] = hotspot.centroid;
      return <g key={hotspot.id}>
        <title>{`Posible foco ${hotspot.id}; ${hotspot.seed_pixels} píxeles semilla`}</title>
        <circle cx={x} cy={y} r="2.5" fill="#FFBB21" stroke="#004254" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
      </g>;
    })}
  </svg>;
}
function ResultViewer({
  result
}) {
  const hasTrueColor = result.input_mode !== 'swir_only';
  const [base, setBase] = useState(hasTrueColor ? 'true-color' : 'swir');
  const [segmentation, setSegmentation] = useState(true);
  const [showFire, setShowFire] = useState(Boolean(result.active_fire?.enabled));
  const [perimeter, setPerimeter] = useState(true);
  const [uncertain, setUncertain] = useState(false);
  const [opacity, setOpacity] = useState(38);
  const [zoom, setZoom] = useState(100);
  const [selected, setSelected] = useState(null);
  const [activeStep, setActiveStep] = useState('overlay');
  const fire = result.active_fire;
  const visibleSteps = fire?.enabled ? [...steps, ...activeFireSteps] : steps;
  const downloads = [['overlay', 'Superposición de cicatriz JPG', 'jpg'], ['mask', 'Máscara binaria PNG', 'png'], ['labels', 'Etiquetas 0 / 1 / 255 PNG', 'png'], ['regions', 'Perímetros JSON', 'json'], ['metadata', 'Análisis y parámetros', 'json'], ['quality', 'Comprobaciones de calidad', 'json']];
  if (fire?.enabled) downloads.splice(1, 0, ['fire_overlay', 'Superposición de focos JPG', 'jpg'], ['fire_mask', 'Máscara de focos PNG', 'png'], ['active_labels', 'Etiquetas 0 / 1 / 2 / 255 PNG', 'png'], ['hotspots', 'Coordenadas de focos JSON', 'json']);
  return <>
    <section className="result-heading" aria-labelledby="result-title">
      <div>
<span className="eyebrow">RESULTADO PARA {result.scene_name}</span>
<h2 id="result-title">Resumen de la escena</h2>
</div>
      <span className="result-badge">
<span />Análisis completado · {number(result.stats.processing_ms / 1000)} s</span>
    </section>
    <div className="stat-grid">
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
    <section className="viewer-card" aria-label="Visor del incendio">
      <div className="viewer-toolbar">
        <div className="segmented" role="group" aria-label="Composición de fondo">
{hasTrueColor && <button type="button" aria-pressed={base === 'true-color'} className={base === 'true-color' ? 'active' : ''} onClick={() => setBase('true-color')}>Color natural</button>}
<button type="button" aria-pressed={base === 'swir'} className={base === 'swir' ? 'active' : ''} onClick={() => setBase('swir')}>SWIR</button>
</div>
        <label className="zoom-label">Zoom <input aria-label="Zoom de la imagen" type="range" min="100" max="300" step="25" value={zoom} onChange={e => setZoom(Number(e.target.value))} />
<span>{zoom}%</span>
</label>
      </div>
      <div className="image-scroll">
        <div className="image-stack" style={{
          width: `${zoom}%`
        }}>
          <img className="base-image" src={result.assets[base]} alt={`Composición ${base === 'swir' ? 'SWIR' : 'en color natural'} de ${result.scene_name}`} />
          {segmentation && <img className="raster-layer" style={{
            opacity: opacity / 100
          }} src={result.assets.layers} alt="" />}
          {uncertain && <div className="uncertainty-layer" style={{
            maskImage: `url(${result.assets.uncertainty})`
          }} />}
          {fire?.enabled && showFire && <img className="fire-raster-layer" src={result.assets.fire_layer} alt="" />}
          {segmentation && perimeter && <Contours result={result} selected={selected} />}
          {fire?.enabled && showFire && <FireMarkers hotspots={fire.hotspots} originalSize={result.original_size} />}
        </div>
      </div>
      <div className="layer-toolbar" role="group" aria-label="Capas del resultado">
        <label>
<input type="checkbox" checked={segmentation} onChange={e => setSegmentation(e.target.checked)} />
<i className="legend-swatch affected-area" />Área posiblemente afectada</label>
        <label>
<input type="checkbox" checked={perimeter} disabled={!segmentation} onChange={e => setPerimeter(e.target.checked)} />
<i className="legend-line" />Perímetro</label>
        <label>
<input type="checkbox" checked={uncertain} onChange={e => setUncertain(e.target.checked)} />
<i className="legend-swatch uncertainty-swatch" />Area de incertidumbre</label>
        {fire?.enabled && <label className="fire-layer-toggle">
<input type="checkbox" checked={showFire} onChange={e => setShowFire(e.target.checked)} />
<i className="legend-swatch fire-yellow" />Posible fuego activo · {number(fire.stats.hotspot_count)}</label>}
        <label className="opacity-label">Opacidad <input aria-label="Opacidad de la máscara" disabled={!segmentation} type="range" min="0" max="90" value={opacity} onChange={e => setOpacity(Number(e.target.value))} />
</label>
      </div>
      <div className="viewer-caption">
<span>{number(result.original_size.width)} × {number(result.original_size.height)} px originales</span>
<span>Máscara: {result.analysis_size.width} × {result.analysis_size.height} px · {number(result.config.pixel_size_m)} m/px original</span>
</div>
    </section>
    <div className="detail-grid">
      <section className="panel regions-panel">
<div className="section-title">
<h3>Regiones detectadas</h3>
<span>{result.regions.length}</span>
</div>
        {result.regions.length ? <div className="region-list">{result.regions.slice(0, 40).map(region => <button type="button" className={`region-row ${selected === region.id ? 'selected' : ''}`} key={region.id} onClick={() => setSelected(selected === region.id ? null : region.id)}>
<span className="region-number">{String(region.id).padStart(2, '0')}</span>
<span>
<strong>Región {region.id}</strong>
<small>{number(region.area_hectares_estimated)} ha estimadas</small>
</span>
<span>{number(region.perimeter_m_estimated / 1000)} km</span>
</button>)}</div> : <p className="muted">No se han encontrado regiones con estos parámetros. Puedes revisar la evidencia y ajustar la sensibilidad.</p>}
        {result.regions.length > 40 && <p className="muted">Se muestran las 40 mayores. La descarga incluye todas las regiones.</p>}
      </section>
      <section className="panel export-panel">
<span className="eyebrow">DATOS PARA SEGUIR TRABAJANDO</span>
<h3>Descargar resultados</h3>
<p>Guarda las máscaras, los perímetros y el resumen de este análisis.</p>
<div className="downloads">{downloads.map(([key, label, extension]) => <a key={key} href={result.assets[key]} download={`brasa-${key}.${extension}`}>{label}<span aria-hidden="true">↗</span>
</a>)}</div>
<p className="unit-note">Escala declarada de {number(result.config.pixel_size_m)} m por píxel original cuadrado. El cálculo compensa la reducción de resolución. Son estimaciones sin georreferenciación.</p>
</section>
    </div>
    {result.quality && <section className="panel quality-panel" aria-label="Calidad del análisis">
<div className="section-title"><h3>Comprobaciones automáticas</h3><span>{result.quality.status === 'usable' ? 'Entrada utilizable' : 'Revisar resultado'}</span></div>
<p>Comprueban la entrada y las condiciones de observación. La precisión de detección requiere máscaras de referencia independientes.</p>
<div className="quality-checks">{result.quality.checks.map(check => <div className={`quality-check ${check.status}`} key={check.id}><strong>{check.status === 'ok' ? '✓' : '△'} {check.label}</strong><p>{check.detail}</p></div>)}</div>
</section>}
    <section className="panel process-panel">
<div className="section-title">
<div>
<span className="eyebrow">UN PROCESO EXPLICABLE</span>
<h3>{fire?.enabled ? 'Del territorio a los focos activos' : 'De la imagen al perímetro'}</h3>
</div>
<span>{visibleSteps.length} pasos</span>
</div>
<div className={`step-list ${fire?.enabled ? 'advanced' : ''}`}>{visibleSteps.map(([key, index, title]) => <button type="button" key={key} className={`step-card ${activeStep === key ? 'selected' : ''}`} onClick={() => setActiveStep(key)}>
<img src={result.assets[key]} alt="" loading="lazy" />
<span>{index}</span>
<strong>{title}</strong>
</button>)}</div>
<div className="step-detail">
<img src={result.assets[activeStep]} alt={visibleSteps.find(([key]) => key === activeStep)[2]} loading="lazy" />
<p>{visibleSteps.find(([key]) => key === activeStep)[3]}</p>
</div>
</section>
    {fire?.enabled && <section className="panel active-fire-summary">
<div className="section-title">
<div><span className="eyebrow">SEÑALES EN EL MOMENTO DE LA CAPTURA</span><h3>Posibles focos activos</h3></div>
<span>{number(fire.stats.hotspot_count)} regiones</span>
</div>
<p>{number(fire.stats.active_pixels)} píxeles candidatos agrupados en focos. Los marcadores amarillos identifican posibles focos; el área afectada aparece en azul.</p>
{fire.hotspots.length > 0 ? <div className="hotspot-list">{fire.hotspots.slice(0, 12).map(hotspot => <div className="hotspot-row" key={hotspot.id}>
<strong>Foco {String(hotspot.id).padStart(2, '0')}</strong>
<span>x {number(hotspot.centroid[0])} · y {number(hotspot.centroid[1])} px</span>
<span>{number(hotspot.area_hectares_estimated)} ha aprox. · {number(hotspot.seed_pixels)} semillas</span>
</div>)}</div> : <p className="muted">No se encontraron píxeles candidatos con estos umbrales. Esto no demuestra que no hubiera fuego activo.</p>}
<ul>{fire.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
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
  function changeInput(action) {
    action();
    setResult(null);
    setError('');
  }
  const selectedScene = scenes.find(scene => scene.id === sceneId);
  const textScale = accessibility.fontSize / 100;
  const accessibilityClasses = `theme-${accessibility.theme} font-${accessibility.fontFamily}`;
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
<a className="brand" href="/" aria-label="Brasa, inicio">
<span className="brand-mark">◒</span>brasa<span className="brand-dot">.</span>
</a>
<div className="topbar-title">INDRA ESPACIO <span>/</span> OBSERVACIÓN SATELITAL</div>
<div className="topbar-actions">
<span className={`connection ${connected ? 'online' : ''}`} role="status" aria-live="polite">
<i aria-hidden="true" />{connected ? 'Servicio disponible' : error ? 'Servicio no disponible' : 'Conectando con el servicio'}</span>
<div className="accessibility-control" ref={accessibilityMenuRef}>
<button ref={accessibilityButtonRef} className="accessibility-trigger" type="button" aria-label="Opciones de accesibilidad" aria-haspopup="dialog" aria-expanded={accessibilityOpen} aria-controls={accessibilityOpen ? 'accessibility-panel' : undefined} onClick={() => setAccessibilityOpen(open => !open)}>
<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="4" r="2" /><path d="m4 9 8-2 8 2M12 7v7m0 0-4 8m4-8 4 8" /></svg>
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
</div>}
</div>
</div>
</header>
    <aside className="sidebar" aria-label="Selección y parámetros del análisis">
<div className="sidebar-intro">
<span className="eyebrow">ANÁLISIS DE INCENDIOS</span>
<h1>Comprender la escena.<br />
<em>Valorar cada señal.</em>
</h1>
<p>Consulta el área posiblemente afectada, su perímetro y las señales compatibles con actividad de fuego.</p>
</div>
      <form onSubmit={submit}>
<fieldset disabled={busy}>
<legend className="visually-hidden">Imágenes y parámetros del análisis</legend>
<div className="segmented source-tabs" role="group" aria-label="Origen de las imágenes">
<button type="button" aria-pressed={mode === 'scenes'} className={mode === 'scenes' ? 'active' : ''} onClick={() => changeInput(() => setMode('scenes'))}>Escenas disponibles</button>
<button type="button" aria-pressed={mode === 'uploads'} className={mode === 'uploads' ? 'active' : ''} onClick={() => changeInput(() => setMode('uploads'))}>Subir imágenes</button>
</div>
        {mode === 'scenes' ? <div className="scene-list">{scenes.map(scene => <button type="button" key={scene.id} className={`scene-card ${sceneId === scene.id ? 'selected' : ''}`} aria-pressed={sceneId === scene.id} onClick={() => changeInput(() => setSceneId(scene.id))}>
<img src={scene.thumbnail_url} alt="" />
<span>
<strong>{scene.name}</strong>
<small>True Color + SWIR</small>
</span>
<i>{sceneId === scene.id ? '●' : '○'}</i>
</button>)}{!scenes.length && <p className="muted">Las escenas aparecerán al conectar con el backend.</p>}</div> : <div className="upload-list">
<div className="segmented source-tabs" role="group" aria-label="Modo de carga">
<button type="button" aria-pressed={uploadMode === 'paired'} className={uploadMode === 'paired' ? 'active' : ''} onClick={() => changeInput(() => setUploadMode('paired'))}>True Color + SWIR</button>
<button type="button" aria-pressed={uploadMode === 'swir_only'} className={uploadMode === 'swir_only' ? 'active' : ''} onClick={() => changeInput(() => { setUploadMode('swir_only'); setTrueFile(null); })}>Solo SWIR</button>
</div>
{uploadMode === 'paired' && <label className="upload-field">
<span>True Color</span>
<small>{trueFile ? trueFile.name : 'Elige un archivo JPEG, PNG o WebP · hasta 80 MB'}</small>
<input type="file" accept="image/jpeg,image/png,image/webp" aria-label="True Color" onChange={event => changeInput(() => setTrueFile(event.target.files[0] || null))} />
</label>}
<label className="upload-field">
<span>Composición SWIR</span>
<small>{swirFile ? swirFile.name : 'Elige un archivo JPEG, PNG o WebP · hasta 80 MB'}</small>
<input type="file" accept="image/jpeg,image/png,image/webp" aria-label="Composición SWIR" onChange={event => changeInput(() => setSwirFile(event.target.files[0] || null))} />
</label>
<p className="muted">{uploadMode === 'paired' ? 'Usa True Color y SWIR de la misma escena, encuadre y momento de captura.' : 'Se analizará únicamente la composición SWIR. No se aplicarán los filtros que necesitan True Color.'}</p>
</div>}
        <div className="analysis-settings">
<div className="setting-title level-title">
<h2>Qué quieres consultar</h2>
<span>CAPAS SEPARADAS</span>
</div>
<p className="analysis-hint">El análisis estima el área afectada y señala posibles focos. Podrás revisar cada resultado por separado.</p>
<div className="setting-title">
<h2>Ajustes de imagen</h2>
<span>OPCIONAL</span>
</div>
<label className="slider-label" htmlFor="sensitivity">Sensibilidad de detección <strong>{sensitivity}%</strong>
</label>
<input id="sensitivity" className="wide-range" type="range" min="0" max="100" value={sensitivity} onChange={e => setSensitivity(Number(e.target.value))} />
<div className="range-labels">
<span>Menos resultados</span>
<span>Más resultados</span>
</div>
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
        <button className="analyze-button" type="submit" disabled={busy || mode === 'scenes' && !scenes.length}>{busy ? <>
<span className="spinner" aria-hidden="true" />Analizando escena · {elapsed} s</> : <>Analizar escena<span aria-hidden="true">↗</span>
</>}</button>
</fieldset>
</form>
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
<h2>Comprender el alcance.<br />
<em>Revisar cada señal.</em>
</h2>
<p>Elige una escena o sube tus imágenes. Consulta el perímetro estimado, las posibles señales de fuego activo y las zonas que requieren revisión.</p>
<div className="welcome-image">{selectedScene && mode === 'scenes' ? <img src={selectedScene.thumbnail_url} alt={`Vista satelital de ${selectedScene.name}`} /> : <div className="upload-placeholder">La escena aparecerá aquí</div>}<div className="image-label">
<span className="live-dot" aria-hidden="true" />{mode === 'scenes' ? selectedScene?.name || 'Escenas disponibles' : 'Tus composiciones satelitales'}<small>COLOR NATURAL</small>
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
