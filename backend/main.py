"""FastAPI service for delineating affected areas in rendered composites."""

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from processing import SegmentationConfig, analyze
from processing.io import MAX_UPLOAD_BYTES, colored_score, read_rgb, write_mask, write_rgb

BASE = Path(__file__).resolve().parent
IMAGES = BASE / "images"
RESULTS = BASE / "results"
PROCESS_LOCK = Lock()
REQUEST_LOCK = Lock()
MAX_RESULTS = 20
SCENES = {"niebla": ("Niebla", "Niebla · Huelva"),
          "la-mierla": ("La_Mierla", "La Mierla"),
          "madrid-avila": ("Madrid-Avila", "Madrid–Ávila")}
ARTIFACTS = {"true-color.jpg", "swir.jpg", "overlay.jpg", "mask.png", "labels.png",
             "uncertainty.png", "score.jpg", "seeds.png", "candidates.png", "grown.png",
             "cleaned.png", "regions.json", "metadata.json", "layers.png", "fire_overlay.jpg",
             "fire_layer.png", "fire_mask.png", "fire_seeds.png", "fire_candidates.png",
             "fire_grown.png", "fire_score.jpg", "active_labels.png", "hotspots.json",
             "fire_context.png", "fire_raw_seeds.png", "quality.json"}
app = FastAPI(title="Brasa · Delimitación de incendios", version="1.0.0")


@contextmanager
def analysis_slot():
    # Reserve before decoding: concurrent large uploads must not all allocate RGB arrays.
    if not REQUEST_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Hay otro análisis en curso. Vuelve a intentarlo al terminar.")
    try:
        yield
    finally:
        REQUEST_LOCK.release()


def remove_result(directory):
    # Resolve and bound every recursive deletion to the explicit result root.
    resolved = directory.resolve()
    if directory.is_symlink() or resolved.parent != RESULTS.resolve():
        raise ValueError("La carpeta de resultados no pertenece al directorio previsto.")
    shutil.rmtree(resolved)


class AnalysisOptions(BaseModel):
    max_side: int = Field(default=1536, ge=256, le=3072)
    sensitivity: float = Field(default=0.5, ge=0, le=1)
    min_area_fraction: float = Field(default=0.00012, ge=0, le=0.02)
    closing_radius: int = Field(default=2, ge=0, le=8)
    refine: bool = True
    active_fire: bool = False
    pixel_size_m: float = Field(default=20.0, gt=0, le=10000, allow_inf_nan=False)


def scene_path(scene_id, kind):
    if scene_id not in SCENES:
        raise HTTPException(404, "Escena desconocida.")
    names = {"true-color": "image_True_color.jpg", "swir": "image_SWIR.jpg", "wildfires": "image_Wildfires.jpg"}
    if kind not in names:
        raise HTTPException(404, "Composición desconocida.")
    path = IMAGES / SCENES[scene_id][0] / names[kind]
    if not path.is_file():
        raise HTTPException(404, "Esta composición no está disponible para la escena.")
    return path


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Motor de análisis disponible"}


@app.get("/api/scenes")
def scenes():
    return [{"id": key, "name": name, "thumbnail_url": f"/api/scenes/{key}/preview/true-color",
             "has_wildfires": (IMAGES / folder / "image_Wildfires.jpg").exists()}
            for key, (folder, name) in SCENES.items()
            if (IMAGES / folder / "image_SWIR.jpg").is_file()]


@app.get("/api/scenes/{scene_id}/preview/{kind}")
def preview(scene_id: str, kind: str):
    from io import BytesIO
    from PIL import Image
    from fastapi.responses import Response

    rgb, _ = read_rgb(scene_path(scene_id, kind), max_side=720)
    buffer = BytesIO()
    Image.fromarray(rgb).save(buffer, format="JPEG", quality=82)
    return Response(buffer.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


def save_analysis(swir, visible, original_size, options, scene_name):
    if not PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Hay otro análisis en curso. Vuelve a intentarlo al terminar.")
    directory = None
    try:
        result = analyze(swir, visible, SegmentationConfig(**options.model_dump(exclude={"active_fire"})),
                         original_size=original_size, active_fire=options.active_fire)
        RESULTS.mkdir(parents=True, exist_ok=True)
        existing = sorted((p for p in RESULTS.iterdir() if p.is_dir() and len(p.name) == 32
                           and all(c in "0123456789abcdef" for c in p.name)), key=lambda p: p.stat().st_mtime)
        for old in existing[:max(0, len(existing) - MAX_RESULTS + 1)]:
            remove_result(old)
        result_id = uuid4().hex
        directory = RESULTS / result_id
        directory.mkdir()
        if result["has_true_color"]:
            write_rgb(directory / "true-color.jpg", result["true_rgb"])
        for name, key in [("swir.jpg", "swir_rgb"), ("overlay.jpg", "overlay")]:
            write_rgb(directory / name, result[key])
        write_mask(directory / "mask.png", result["mask"] * 255)
        write_mask(directory / "labels.png", result["labels"])
        write_mask(directory / "uncertainty.png", result["uncertain"] * 255)
        layers = np.zeros((*result["mask"].shape, 4), dtype=np.uint8)
        layers[result["mask"]] = [3, 108, 124, 255]
        from PIL import Image
        Image.fromarray(layers).save(directory / "layers.png")
        write_rgb(directory / "score.jpg", colored_score(result["steps"]["score"]))
        for key in ["seeds", "candidates", "grown", "cleaned"]:
            write_mask(directory / f"{key}.png", result["steps"][key] * 255)
        fire = result["active_fire"]
        if fire is not None:
            write_rgb(directory / "fire_overlay.jpg", fire["overlay"])
            write_mask(directory / "fire_mask.png", fire["mask"] * 255)
            write_mask(directory / "fire_seeds.png", fire["seeds"] * 255)
            write_mask(directory / "fire_raw_seeds.png", fire["raw_seeds"] * 255)
            write_mask(directory / "fire_context.png", fire["context_support"] * 255)
            write_mask(directory / "fire_candidates.png", fire["candidates"] * 255)
            write_mask(directory / "fire_grown.png", fire["grown"] * 255)
            write_rgb(directory / "fire_score.jpg", colored_score(fire["score"]))
            write_mask(directory / "active_labels.png", fire["labels"])
            fire_layer = np.zeros((*fire["mask"].shape, 4), dtype=np.uint8)
            fire_layer[fire["mask"]] = [227, 52, 47, 255]
            Image.fromarray(fire_layer).save(directory / "fire_layer.png")
            fire_geometry = {"coordinate_system": "image_pixels", "original_size": result["original_size"],
                             "analysis_size": result["analysis_size"], "hotspots": fire["hotspots"]}
        geometry = {"coordinate_system": "image_pixels", "original_size": result["original_size"],
                    "analysis_size": result["analysis_size"], "regions": result["regions"]}
        geometry["spatial_resolution"] = result["spatial_resolution"]
        (directory / "regions.json").write_text(json.dumps(geometry, ensure_ascii=False), encoding="utf-8")
        if fire is not None:
            fire_geometry["spatial_resolution"] = result["spatial_resolution"]
            (directory / "hotspots.json").write_text(json.dumps(fire_geometry, ensure_ascii=False), encoding="utf-8")
        metadata = {key: result[key] for key in ["config", "original_size", "analysis_size", "coarse_size", "stats", "warnings", "regions", "quality", "spatial_resolution"]}
        (directory / "quality.json").write_text(json.dumps(result["quality"], ensure_ascii=False), encoding="utf-8")
        available_artifacts = set(ARTIFACTS)
        if not result["has_true_color"]:
            available_artifacts.discard("true-color.jpg")
        if fire is None:
            available_artifacts.difference_update({
                "fire_overlay.jpg", "fire_layer.png", "fire_mask.png", "fire_seeds.png",
                "fire_candidates.png", "fire_grown.png", "fire_score.jpg", "active_labels.png",
                "hotspots.json", "fire_context.png", "fire_raw_seeds.png",
            })
        assets = {name.split(".")[0]: f"/api/results/{result_id}/{name}"
                  for name in sorted(available_artifacts)}
        fire_asset_names = {
            "fire_overlay", "fire_layer", "fire_mask", "fire_seeds", "fire_candidates",
            "fire_grown", "fire_score", "active_labels", "hotspots", "fire_context", "fire_raw_seeds",
        }
        metadata.update({"result_id": result_id, "scene_name": scene_name,
                         "input_mode": result["input_mode"],
                         "algorithm": "colour-hysteresis+multiscale-fire-context-soft-uncertainty-v4" if fire is not None else "colour-hysteresis-v2",
                         "assets": assets,
                         "active_fire": {
                             "enabled": fire is not None,
                             "config": fire["config"] if fire is not None else None,
                             "stats": fire["stats"] if fire is not None else {"seed_pixels": 0, "candidate_pixels": 0, "active_pixels": 0, "active_percent": 0, "hotspot_count": 0},
                             "hotspots": fire["hotspots"] if fire is not None else [],
                             "warnings": fire["warnings"] if fire is not None else [],
                             "assets": {key: value for key, value in assets.items() if key in fire_asset_names},
                         },
                         "step_descriptions": ["Composición SWIR", "Evidencia de color", "Semillas fuertes",
                                               "Candidatos", "Crecimiento conectado", "Limpieza", "Perímetro final"],
                         })
        (directory / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return metadata
    except ValueError as exc:
        if directory:
            remove_result(directory)
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        if directory:
            remove_result(directory)
        raise
    finally:
        PROCESS_LOCK.release()


@app.post("/api/scenes/{scene_id}/analyze")
def analyze_scene(scene_id: str, options: AnalysisOptions):
    with analysis_slot():
        return process_scene(scene_id, options)


def process_scene(scene_id, options):
    try:
        swir, size = read_rgb(scene_path(scene_id, "swir"))
        visible, visible_size = read_rgb(scene_path(scene_id, "true-color"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if size != visible_size:
        raise HTTPException(422, "Las composiciones tienen dimensiones originales distintas.")
    return save_analysis(swir, visible, size, options, SCENES[scene_id][1])


async def upload_bytes(upload):
    content = bytearray()
    while chunk := await upload.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Cada imagen puede ocupar como máximo 80 MB.")
    return bytes(content)


@app.post("/api/process")
async def process_images(image1: UploadFile | None = File(None), image2: UploadFile | None = File(None),
                         input_mode: str = Form("paired"),
                         sensitivity: float = Form(0.5), max_side: int = Form(1536),
                         refine: bool = Form(True), active_fire: bool = Form(False), pixel_size_m: float = Form(20.0)):
    with analysis_slot():
        return await process_upload(image1, image2, sensitivity, max_side, refine, active_fire, pixel_size_m, input_mode)


async def process_upload(image1, image2, sensitivity, max_side, refine, active_fire, pixel_size_m, input_mode="paired"):
    try:
        if input_mode not in {"paired", "swir_only"}:
            raise ValueError("El modo de carga debe ser 'paired' o 'swir_only'.")
        if image2 is None:
            raise ValueError("Selecciona una composición SWIR.")
        if input_mode == "paired" and image1 is None:
            raise ValueError("Selecciona True Color y SWIR, o cambia el modo a Solo SWIR.")
        options = AnalysisOptions(sensitivity=sensitivity, max_side=max_side, refine=refine,
                                  active_fire=active_fire, pixel_size_m=pixel_size_m)
        swir, size = await run_in_threadpool(read_rgb, await upload_bytes(image2))
        visible = None
        scene_name = "Imagen SWIR subida"
        if input_mode == "paired":
            visible, visible_size = await run_in_threadpool(read_rgb, await upload_bytes(image1))
            if size != visible_size:
                raise ValueError("True Color y SWIR deben tener las mismas dimensiones originales.")
            scene_name = "Imágenes subidas"
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await run_in_threadpool(save_analysis, swir, visible, size, options, scene_name)


@app.get("/api/results/{result_id}/{artifact}")
def artifact(result_id: str, artifact: str):
    if len(result_id) != 32 or any(c not in "0123456789abcdef" for c in result_id) or artifact not in ARTIFACTS:
        raise HTTPException(404, "Resultado desconocido.")
    path = RESULTS / result_id / artifact
    if not path.is_file():
        raise HTTPException(404, "El resultado ya no está disponible. Se conservan los últimos 20 análisis.")
    return FileResponse(path, filename=artifact, content_disposition_type="inline")
