"""Reproducible scene evaluation; stability never substitutes for ground truth."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
from PIL import Image

from processing import SegmentationConfig, analyze
from processing.active_fire import ActiveFireConfig, detect_active_fire
from processing.evaluation import evaluate_mask, evaluate_components
from processing.io import read_rgb, write_rgb


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def stability(baseline, variant):
    mask = cv2.resize(variant.astype(np.uint8), (baseline.shape[1], baseline.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
    union = (baseline | mask).sum()
    return {"iou_self_consistency": float((baseline & mask).sum() / union) if union else 1.0,
            "both_empty": bool(not union)}


def reference_metrics(spec, root, result):
    metrics = {}
    for kind, predicted in [("affected", result['mask']), ("active", result['active_fire']['mask'])]:
        entry = spec.get('references', {}).get(kind)
        if entry is None:
            metrics[kind] = {"status": "not_provided", "pixel": None, "components": None}
            continue
        path = root / entry['path']
        reference = np.asarray(Image.open(path))
        grid = entry.get('grid', 'analysis')
        expected = (result['original_size']['height'], result['original_size']['width']) if grid == 'original' else predicted.shape
        if grid not in {'original', 'analysis'} or reference.shape != expected or not np.isin(reference, [0, 1, 255]).all():
            raise ValueError(f"Referencia {kind} inválida: cuadrícula declarada y valores 0/1/255 requeridos.")
        # Explicit original grid is resampled by nearest neighbor, with the operation reported.
        if grid == 'original':
            reference = cv2.resize(reference, (predicted.shape[1], predicted.shape[0]), interpolation=cv2.INTER_NEAREST)
        metrics[kind] = {"status": "evaluated", "reference_sha256": digest(path), "reference_grid": grid,
                         "evaluation_grid": result['analysis_size'], "pixel": evaluate_mask(predicted, reference),
                         "components": evaluate_components(predicted, reference) if kind == 'active' else None}
    return metrics


def variants(swir, visible):
    for factor in (.9, 1.1):
        yield f'brightness_{factor}', tuple(np.clip(a.astype(np.float32) * factor, 0, 255).astype(np.uint8) for a in (swir, visible))
    encoded = []
    for array in (swir, visible):
        buffer = io.BytesIO()
        Image.fromarray(array).save(buffer, format='JPEG', quality=70)
        encoded.append(np.asarray(Image.open(io.BytesIO(buffer.getvalue())).convert('RGB')))
    yield 'jpeg_quality_70', encoded
    yield 'scale_075', tuple(cv2.resize(a, None, fx=.75, fy=.75, interpolation=cv2.INTER_AREA) for a in (swir, visible))


def run(manifest_path, output, robustness=False):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    config = SegmentationConfig(**manifest['config'])
    output.mkdir(parents=True, exist_ok=True)
    report = {"algorithm": "colour-hysteresis+rgb-context-v2", "config": config.to_dict(),
              "manifest_sha256": digest(manifest_path),
              "code_sha256": {p.name: digest(p) for p in sorted((Path(__file__).parent / 'processing').glob('*.py'))},
              "interpretation": "La estabilidad mide consistencia ante perturbaciones, no precisión. Sin referencias independientes no se mide generalización.",
              "scenes": [], "stability_review_threshold": .6}
    for scene in manifest['scenes']:
        if scene['split'] not in {'development', 'holdout'}:
            raise ValueError('split debe ser development o holdout.')
        paths = [manifest_path.parent / scene[k] for k in ['swir', 'true_color']]
        (swir, size), (visible, visible_size) = [read_rgb(p) for p in paths]
        if size != visible_size:
            raise ValueError('Dimensiones originales distintas.')
        start = perf_counter()
        result = analyze(swir, visible, config, original_size=size, active_fire=True)
        raw = detect_active_fire(result['swir_rgb'], result['uncertain'], size, ActiveFireConfig(contextual_filter=False))
        row = {"id": scene['id'], "split": scene['split'], "input_sha256": dict(zip(['swir', 'true_color'], map(digest, paths))),
               "stats": result['stats'], "active_stats": result['active_fire']['stats'], "quality": result['quality'],
               "metrics": reference_metrics(scene, manifest_path.parent, result),
               "context_filter_comparison": {"without_context_hotspots": raw['stats']['hotspot_count'],
                                             "with_context_hotspots": result['active_fire']['stats']['hotspot_count'],
                                             "interpretation": "Reducción de candidatos; no equivale a reducción medida de falsos positivos."},
               "stability": {}, "seconds": round(perf_counter() - start, 2)}
        # File names are generated locally, never from a manifest path or scene ID.
        write_rgb(output / f"scene_{len(report['scenes']) + 1}_overlay.jpg", result['active_fire']['overlay'])
        if robustness:
            for name, (s, v) in variants(swir, visible):
                changed = analyze(s, v, config, original_size=size, active_fire=True)
                row['stability'][name] = {"affected": stability(result['mask'], changed['mask']),
                                          "active": stability(result['active_fire']['mask'], changed['active_fire']['mask'])}
        row['stability_review'] = [f'{name}/{layer}' for name, value in row['stability'].items()
                                   for layer in ['affected', 'active'] if value[layer]['iou_self_consistency'] < report['stability_review_threshold']]
        report['scenes'].append(row)
        print(f"{scene['id']}: {row['stats']['region_count']} regiones, {row['active_stats']['hotspot_count']} focos candidatos", flush=True)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Evaluación reproducible', '', report['interpretation'], '',
             f'Escala declarada: {config.pixel_size_m:g} m/píxel original; se compensa el remuestreo. Área y perímetro son estimados.', '',
             '| Escena | Partición | Regiones | Área ha | Perímetro km | Focos sin/con contexto | Referencias |',
             '|---|---|---:|---:|---:|---|---|']
    for row in report['scenes']:
        stats, comparison = row['stats'], row['context_filter_comparison']
        refs = ', '.join(f"{k}: {v['status']}" for k, v in row['metrics'].items())
        lines.append(f"| {row['id']} | {row['split']} | {stats['region_count']} | {stats['affected_area_hectares_estimated']:.1f} | {stats['perimeter_m_estimated']/1000:.1f} | {comparison['without_context_hotspots']}/{comparison['with_context_hotspots']} | {refs} |")
    lines += ['', '## Estabilidad (IoU respecto al resultado original, no exactitud)', '',
              '| Escena | Perturbación | Cicatriz | Focos |', '|---|---|---:|---:|']
    for row in report['scenes']:
        for name, value in row['stability'].items():
            lines.append(f"| {row['id']} | {name} | {value['affected']['iou_self_consistency']:.3f} | {value['active']['iou_self_consistency']:.3f} |")
    lines += ['', 'Los pares con ambas máscaras vacías tienen estabilidad 1; no acreditan detección correcta.',
              'Las escenas de desarrollo no son un conjunto de validación independiente. Mantener umbrales fijos y separar incidentes nuevos como holdout antes de observar sus resultados.',
              'El humo puede ocultar focos. El contraste local puede perder frentes extensos. Suelo rojo y superficies urbanas pueden seguir generando candidatos.',
              'La exactitud se calcula solo cuando el manifiesto incluye referencias manuales independientes; Wildfires no es una referencia cuantitativa.']
    for row in report['scenes']:
        if row['stability_review']:
            lines.append(f"Revisar estabilidad en {row['id']} (IoU < 0,6): {', '.join(row['stability_review'])}.")
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).parent / 'evaluation' / 'manifest.json')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'evaluation' / 'latest')
    parser.add_argument('--robustness', action='store_true')
    args = parser.parse_args()
    run(args.manifest.resolve(), args.output.resolve(), args.robustness)
