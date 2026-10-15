"""FastAPI service for delineating affected areas in rendered composites."""

import json
import shutil
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
MAX_RESULTS = 20
SCENES = {"niebla": ("Niebla", "Niebla · Huelva"),
          "la-mierla": ("La_Mierla", "La Mierla"),
          "madrid-avila": ("Madrid-Avila", "Madrid–Ávila")}
ARTIFACTS = {"true-color.jpg", "swir.jpg", "overlay.jpg", "mask.png", "labels.png",
             "uncertainty.png", "score.jpg", "seeds.png", "candidates.png", "grown.png",
             "cleaned.png", "regions.json", "metadata.json", "layers.png"}
app = FastAPI(title="Brasa · Delimitación de incendios", version="1.0.0")


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
        result = analyze(swir, visible, SegmentationConfig(**options.model_dump()), original_size=original_size)
        RESULTS.mkdir(parents=True, exist_ok=True)
        existing = sorted((p for p in RESULTS.iterdir() if p.is_dir() and len(p.name) == 32
                           and all(c in "0123456789abcdef" for c in p.name)), key=lambda p: p.stat().st_mtime)
        for old in existing[:max(0, len(existing) - MAX_RESULTS + 1)]:
            remove_result(old)
        result_id = uuid4().hex
        directory = RESULTS / result_id
        directory.mkdir()
        for name, key in [("true-color.jpg", "true_rgb"), ("swir.jpg", "swir_rgb"), ("overlay.jpg", "overlay")]:
            write_rgb(directory / name, result[key])
        write_mask(directory / "mask.png", result["mask"] * 255)
        write_mask(directory / "labels.png", result["labels"])
        write_mask(directory / "uncertainty.png", result["uncertain"] * 255)
        layers = np.zeros((*result["mask"].shape, 4), dtype=np.uint8)
        layers[result["mask"]] = [249, 126, 40, 255]
        from PIL import Image
        Image.fromarray(layers).save(directory / "layers.png")
        write_rgb(directory / "score.jpg", colored_score(result["steps"]["score"]))
        for key in ["seeds", "candidates", "grown", "cleaned"]:
            write_mask(directory / f"{key}.png", result["steps"][key] * 255)
        geometry = {"coordinate_system": "image_pixels", "original_size": result["original_size"],
                    "analysis_size": result["analysis_size"], "regions": result["regions"]}
        (directory / "regions.json").write_text(json.dumps(geometry, ensure_ascii=False), encoding="utf-8")
        metadata = {key: result[key] for key in ["config", "original_size", "analysis_size", "coarse_size", "stats", "warnings", "regions"]}
        metadata.update({"result_id": result_id, "scene_name": scene_name, "algorithm": "colour-hysteresis-v1",
                         "assets": {name.split(".")[0]: f"/api/results/{result_id}/{name}" for name in sorted(ARTIFACTS)},
                         "step_descriptions": ["Composición SWIR", "Evidencia de color", "Semillas fuertes",
                                               "Candidatos", "Crecimiento conectado", "Limpieza", "Perímetro final"]})
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
async def process_images(image1: UploadFile = File(...), image2: UploadFile = File(...),
                         sensitivity: float = Form(0.5), max_side: int = Form(1536),
                         refine: bool = Form(True)):
    # Existing fields: image1=True Color, image2=SWIR.
    try:
        options = AnalysisOptions(sensitivity=sensitivity, max_side=max_side, refine=refine)
        visible, visible_size = await run_in_threadpool(read_rgb, await upload_bytes(image1))
        swir, size = await run_in_threadpool(read_rgb, await upload_bytes(image2))
        if size != visible_size:
            raise ValueError("True Color y SWIR deben tener las mismas dimensiones originales.")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await run_in_threadpool(save_analysis, swir, visible, size, options, "Imágenes subidas")


@app.get("/api/results/{result_id}/{artifact}")
def artifact(result_id: str, artifact: str):
    if len(result_id) != 32 or any(c not in "0123456789abcdef" for c in result_id) or artifact not in ARTIFACTS:
        raise HTTPException(404, "Resultado desconocido.")
    path = RESULTS / result_id / artifact
    if not path.is_file():
        raise HTTPException(404, "El resultado ya no está disponible. Se conservan los últimos 20 análisis.")
    return FileResponse(path, filename=artifact, content_disposition_type="inline")
