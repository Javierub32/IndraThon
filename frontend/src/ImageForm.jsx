import { useEffect, useState } from 'react';
const number = value => new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 1
}).format(value);
const steps = [['swir', '01', 'Composición SWIR', 'La entrada de color que utilizamos para localizar la cicatriz.'], ['score', '02', 'Evidencia de color', 'Azul: evidencia baja. Rojo: evidencia alta. No es una probabilidad calibrada.'], ['seeds', '03', 'Semillas', 'Píxeles que superan el umbral más estricto.'], ['candidates', '04', 'Candidatos', 'Superficies compatibles con el umbral permisivo.'], ['grown', '05', 'Regiones conectadas', 'Candidatos conectados con al menos una semilla.'], ['cleaned', '06', 'Limpieza', 'Filtrado de componentes y relleno limitado de huecos.'], ['overlay', '07', 'Perímetro final', 'Resultado tras el refinamiento opcional de los límites.']];
const activeFireSteps = [['fire_score', '08', 'Contraste del render', 'Brillo rojo y contraste R/B; la equivalencia con bandas espectrales depende del render. No es temperatura.'], ['fire_raw_seeds', '09', 'Semillas cromáticas', 'Primer filtro fijo de brillo y relación entre canales.'], ['fire_context', '10', 'Contraste local', 'Semillas anómalamente brillantes frente al fondo local. Ayuda a descartar superficies rojas uniformes.'], ['fire_seeds', '11', 'Semillas aceptadas', 'Componentes de semillas con apoyo contextual.'], ['fire_candidates', '12', 'Candidatos activos', 'Píxeles compatibles con los umbrales permisivos.'], ['fire_grown', '13', 'Crecimiento limitado', 'Las semillas se expanden hasta dos pasos dentro de los candidatos.'], ['fire_mask', '14', 'Focos posibles', 'Componentes de actividad aparente, dibujados en magenta.']];
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Revisa las imágenes y los parámetros del análisis.';
    throw new Error(detail);
  }
  return data;
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
      return <path key={region.id} d={path} fill="none" stroke={selected === region.id ? '#ffffff' : '#ffe3a0'} strokeWidth={selected === region.id ? 3 : 1.5} vectorEffect="non-scaling-stroke" />;
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
        <circle cx={x} cy={y} r="2" fill="#f42389" stroke="#f42389" strokeWidth="3" vectorEffect="non-scaling-stroke" />
      </g>;
    })}
  </svg>;
}
function ResultViewer({
  result
}) {
  const [base, setBase] = useState('true-color');
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
    <section className="result-heading">
      <div>
<span className="eyebrow">RESULTADO DEL ANÁLISIS</span>
<h2>{result.scene_name}</h2>
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
<span>Zona incierta</span>
<strong>{number(result.stats.uncertain_percent)}<small>%</small>
</strong>
<p>humo, nube o falta de datos estimados</p>
</div>
    </div>
    <section className="viewer-card" aria-label="Visor del incendio">
      <div className="viewer-toolbar">
        <div className="segmented">
<button type="button" className={base === 'true-color' ? 'active' : ''} onClick={() => setBase('true-color')}>Color natural</button>
<button type="button" className={base === 'swir' ? 'active' : ''} onClick={() => setBase('swir')}>SWIR</button>
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
      <div className="layer-toolbar">
        <label>
<input type="checkbox" checked={segmentation} onChange={e => setSegmentation(e.target.checked)} />
<i className="legend-swatch orange" />Segmentación</label>
        <label>
<input type="checkbox" checked={perimeter} disabled={!segmentation} onChange={e => setPerimeter(e.target.checked)} />
<i className="legend-line" />Perímetro</label>
        <label>
<input type="checkbox" checked={uncertain} onChange={e => setUncertain(e.target.checked)} />
<i className="legend-swatch blue" />Incertidumbre</label>
        {fire?.enabled && <label className="fire-layer-toggle">
<input type="checkbox" checked={showFire} onChange={e => setShowFire(e.target.checked)} />
<i className="legend-swatch fire-pink" />Posible fuego activo · {number(fire.stats.hotspot_count)}</label>}
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
<span className="eyebrow">LLEVA EL RESULTADO CONTIGO</span>
<h3>Exportar análisis</h3>
<p>Máscaras, límites y parámetros para seguir trabajando con el resultado.</p>
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
<div><span className="eyebrow">RETO AVANZADO · ACTIVIDAD EN LA ADQUISICIÓN</span><h3>Posibles focos activos</h3></div>
<span>{number(fire.stats.hotspot_count)} regiones</span>
</div>
<p>{number(fire.stats.active_pixels)} píxeles candidatos agrupados en focos. Los marcadores magenta son distintos de la superficie afectada naranja.</p>
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
    if (mode === 'uploads' && (!trueFile || !swirFile)) {
      setError('Selecciona las dos composiciones: True Color y SWIR.');
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
        form.append('image1', trueFile);
        form.append('image2', swirFile);
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
  return <div className="app-shell">
    <header className="topbar">
<a className="brand" href="/" aria-label="Brasa, inicio">
<span className="brand-mark">◒</span>brasa<span className="brand-dot">.</span>
</a>
<div className="topbar-title">OBSERVACIÓN SATELITAL <span>/</span> ANÁLISIS DE INCENDIOS</div>
<span className={`connection ${connected ? 'online' : ''}`}>
<i />{connected ? 'Motor conectado' : 'Conectando'}</span>
</header>
    <aside className="sidebar">
<div className="sidebar-intro">
<span className="eyebrow">ESPACIO DE TRABAJO</span>
<h1>Leer el territorio.<br />
<em>Delimitar el impacto.</em>
</h1>
<p>Transforma una composición satelital en una delimitación visible y explicable.</p>
</div>
      <form onSubmit={submit}>
<fieldset disabled={busy}>
<div className="segmented source-tabs">
<button type="button" className={mode === 'scenes' ? 'active' : ''} onClick={() => changeInput(() => setMode('scenes'))}>Escenas de ejemplo</button>
<button type="button" className={mode === 'uploads' ? 'active' : ''} onClick={() => changeInput(() => setMode('uploads'))}>Subir imágenes</button>
</div>
        {mode === 'scenes' ? <div className="scene-list">{scenes.map(scene => <button type="button" key={scene.id} className={`scene-card ${sceneId === scene.id ? 'selected' : ''}`} aria-pressed={sceneId === scene.id} onClick={() => changeInput(() => setSceneId(scene.id))}>
<img src={scene.thumbnail_url} alt="" />
<span>
<strong>{scene.name}</strong>
<small>True Color + SWIR</small>
</span>
<i>{sceneId === scene.id ? '●' : '○'}</i>
</button>)}{!scenes.length && <p className="muted">Las escenas aparecerán al conectar con el backend.</p>}</div> : <div className="upload-list">{[['True Color', trueFile, setTrueFile], ['Composición SWIR', swirFile, setSwirFile]].map(([label, file, setter]) => <label className="upload-field" key={label}>
<span>{label}</span>
<small>{file ? file.name : 'JPEG, PNG o WebP · hasta 80 MB'}</small>
<input type="file" accept="image/jpeg,image/png,image/webp" aria-label={label} onChange={event => changeInput(() => setter(event.target.files[0] || null))} />
</label>)}<p className="muted">Mismo tamaño, encuadre y adquisición. Selecciona las composiciones en el orden indicado.</p>
</div>}
        <div className="analysis-settings">
<div className="setting-title level-title">
<h2>Análisis completo</h2>
<span>CAPAS INDEPENDIENTES</span>
</div>
<p className="analysis-hint">Calcula la segmentación y el posible fuego activo. Puedes activar cada capa por separado o ver ambas simultáneamente en el visor.</p>
<div className="setting-title">
<h2>Parámetros del análisis</h2>
<span>CLÁSICO · RGB</span>
</div>
<label className="slider-label" htmlFor="sensitivity">Sensibilidad <strong>{sensitivity}%</strong>
</label>
<input id="sensitivity" className="wide-range" type="range" min="0" max="100" value={sensitivity} onChange={e => setSensitivity(Number(e.target.value))} />
<div className="range-labels">
<span>Más conservador</span>
<span>Más inclusivo</span>
</div>
<label className="select-label" htmlFor="resolution">Resolución de detección<select id="resolution" value={resolution} onChange={e => setResolution(Number(e.target.value))}>
<option value="1024">1024 px · rápida</option>
<option value="1536">1536 px · equilibrada</option>
<option value="2048">2048 px · detallada</option>
</select>
</label>
<label className="select-label" htmlFor="pixel-size">Metros por píxel original<input id="pixel-size" type="number" min="0.01" max="10000" step="any" required value={pixelSize} onChange={e => setPixelSize(e.target.value === '' ? '' : Number(e.target.value))} /></label>
<p className="analysis-hint">Sentinel: 20 m/px. Ajusta la escala si la exportación fue remuestreada.</p>
<label className="refine-option">
<input type="checkbox" checked={refine} onChange={e => setRefine(e.target.checked)} />
<span>Refinar los límites<small>Segunda pasada a mayor resolución</small>
</span>
</label>
</div>
        <button className="analyze-button" type="submit" disabled={busy || mode === 'scenes' && !scenes.length}>{busy ? <>
<span className="spinner" />Analizando · {elapsed} s</> : <>Analizar imágenes<span aria-hidden="true">↗</span>
</>}</button>
</fieldset>
</form>
<div className="sidebar-foot">
<span className="tiny-mark">◉</span>
<p>Sentinel-2 · Composiciones de visualización<br />Retos básico y avanzado · Malackathon 2026</p>
</div>
    </aside>
    <main className="main-content">{error && <div className="error-banner" role="alert">{error}</div>}{busy && <div className="progress-banner" role="status">
<span className="spinner" />Calculando la segmentación y los posibles focos activos. El resultado aparecerá al terminar.</div>}
      {result ? <ResultViewer key={result.result_id} result={result} /> : <section className="welcome">
<div className="welcome-top">
<span className="eyebrow">DELIMITACIÓN DE LA SUPERFICIE AFECTADA</span>
<span className="edition">01 / EXPLORAR</span>
</div>
<h2>La huella del incendio,<br />
<em>sobre el terreno.</em>
</h2>
<p>Selecciona una escena y analiza la composición SWIR. Explora la superficie detectada, sus límites y la evidencia de cada paso.</p>
<div className="welcome-image">{selectedScene && mode === 'scenes' ? <img src={selectedScene.thumbnail_url} alt={`Vista satelital de ${selectedScene.name}`} /> : <div className="upload-placeholder">Dos imágenes. Una misma escena.</div>}<div className="image-label">
<span className="live-dot" />{mode === 'scenes' ? selectedScene?.name || 'Cargando escenas' : 'Tus composiciones satelitales'}<small>COLOR NATURAL</small>
</div>
</div>
<div className="welcome-features">
<div>
<span>01</span>
<strong>Detectar</strong>
<p>Color y contraste en la composición SWIR.</p>
</div>
<div>
<span>02</span>
<strong>Delimitar</strong>
<p>Regiones conectadas y perímetros con huecos.</p>
</div>
<div>
<span>03</span>
<strong>Interpretar</strong>
<p>Capas, incertidumbre y resultados descargables.</p>
</div>
</div>
<p className="welcome-note">Este análisis estima evidencias de afectación. Las medidas usan la escala declarada de {number(pixelSize || 20)} m por píxel original; los colores del JPEG no son reflectancias.</p>
</section>}
      <footer className="main-footer">
<span>BRASA / LABORATORIO DE OBSERVACIÓN</span>
<span>Del píxel a una decisión informada.</span>
</footer>
    </main>
  </div>;
}
