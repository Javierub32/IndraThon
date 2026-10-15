"""Bounded decoding of display composites, preserving source dimensions."""
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_SOURCE_PIXELS = 85_000_000


def read_rgb(source, max_side=4096):
    try:
        handle = BytesIO(source) if isinstance(source, bytes) else Path(source)
        with Image.open(handle) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Usa una composición JPEG, PNG o WebP de tres canales.")
            original_size = image.size
            if min(original_size) < 32 or original_size[0] * original_size[1] > MAX_SOURCE_PIXELS:
                raise ValueError("La imagen debe tener al menos 32 × 32 píxeles y como máximo 85 megapíxeles.")
            if image.getexif().get(274, 1) != 1:
                raise ValueError("Exporta las composiciones sin rotación EXIF para conservar su correspondencia.")
            factor = min(1.0, max_side / max(original_size))
            target = tuple(max(1, round(value * factor)) for value in original_size)
            image.draft("RGB", target)
            image = image.convert("RGB")
            if image.size != target:
                image = image.resize(target, Image.Resampling.LANCZOS)
            return np.array(image), original_size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("No se pudo leer la imagen. Usa un JPEG, PNG o WebP válido.") from exc


def write_rgb(path, rgb):
    Image.fromarray(rgb).save(path)


def write_mask(path, mask):
    Image.fromarray(mask.astype(np.uint8)).save(path)


def colored_score(score):
    colored = cv2.applyColorMap(np.round(np.clip(score, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    return cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
