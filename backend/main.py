import base64

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI()

@app.get("/api/health")
def health():
    return {"message": "React y FastAPI están conectados"}

def aplicar_canny(contenido: bytes) -> str:
    datos = np.frombuffer(contenido, dtype=np.uint8)
    imagen = cv2.imdecode(datos, cv2.IMREAD_COLOR)

    if imagen is None:
        raise HTTPException(status_code=400, detail="No se pudo leer una imagen.")

    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    bordes = cv2.Canny(gris, 100, 200)

    correcto, png = cv2.imencode(".png", bordes)
    if not correcto:
        raise HTTPException(status_code=500, detail="No se pudo codificar el resultado.")

    return "data:image/png;base64," + base64.b64encode(png.tobytes()).decode("ascii")


@app.post("/api/process")
async def procesar_imagenes(
    image1: UploadFile = File(...),
    image2: UploadFile = File(...),
):
    resultado1 = aplicar_canny(await image1.read())
    resultado2 = aplicar_canny(await image2.read())

    return {
        "image1": resultado1,
        "image2": resultado2,
    }