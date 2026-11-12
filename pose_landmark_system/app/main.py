from __future__ import annotations

import base64
from contextlib import asynccontextmanager
import json
import os
import re
import uuid
from pathlib import Path
from typing import Literal
import zipfile

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response

from .coco_export import build_coco_keypoints_zip
from .inference import InferenceEngine
from .rendering import render_predictions
from .schema import APP_ROOT


MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", "10485760"))
MAX_BATCH_IMAGES = 50
MAX_BATCH_BYTES = 100_000_000
MAX_IMAGE_PIXELS = 25_000_000
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", APP_ROOT / "outputs")).expanduser()
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = (APP_ROOT / OUTPUT_DIR).resolve()
OUTPUT_DIR = OUTPUT_DIR.resolve()
PROTECTED_OUTPUTS = (
    APP_ROOT.parent / "data",
    APP_ROOT.parent / "src" / "lab" / "images",
    APP_ROOT.parent / "src" / "exports",
)
if any(path.resolve() == OUTPUT_DIR or path.resolve() in OUTPUT_DIR.parents for path in PROTECTED_OUTPUTS):
    raise ValueError(f"Refusing to save predictions in a protected lab directory: {OUTPUT_DIR}")

engine = InferenceEngine()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    engine.close()


app = FastAPI(title="Face Landmarks and Person Pose Demo", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (APP_ROOT / "app" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/predict")
async def predict(
    image: UploadFile = File(...),
    mode: Literal["face", "person", "both"] = Form("both"),
    save_result: bool = Form(False),
) -> dict:
    raw_image = await _read_upload(image)
    record, rendered_bytes = _infer_image(raw_image, mode)
    result = _response_record(record, rendered_bytes)
    if save_result:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        result_id = uuid.uuid4().hex
        image_path = OUTPUT_DIR / f"{result_id}.jpg"
        json_path = OUTPUT_DIR / f"{result_id}.json"
        image_path.write_bytes(rendered_bytes)
        saved_result = {
            key: value
            for key, value in result.items()
            if key != "image_jpeg_base64"
        }
        json_path.write_text(
            json.dumps(saved_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["saved_files"] = {
            "image": image_path.name,
            "predictions": json_path.name,
        }

    return result


async def _read_upload(image: UploadFile) -> bytes:
    raw_image = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_image) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the {MAX_UPLOAD_BYTES}-byte upload limit.",
        )
    if not raw_image:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    return raw_image


def _infer_image(raw_image: bytes, mode: str) -> tuple[dict, bytes]:
    decoded = cv2.imdecode(np.frombuffer(raw_image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise HTTPException(
            status_code=415, detail="Upload must be a readable image file."
        )
    height, width = decoded.shape[:2]
    if height * width > MAX_IMAGE_PIXELS:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the {MAX_IMAGE_PIXELS}-pixel limit.",
        )
    try:
        predictions = engine.predict(decoded, mode)
    except (FileNotFoundError, ImportError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    rendered = render_predictions(decoded, predictions, engine.schemas)
    success, encoded = cv2.imencode(".jpg", rendered)
    if not success:
        raise HTTPException(status_code=500, detail="Could not encode result image.")
    record = {
        "image_width": width,
        "image_height": height,
        "counts": {
            "face": sum(item.kind == "face" for item in predictions),
            "person": sum(item.kind == "person" for item in predictions),
        },
        "predictions": [item.to_dict() for item in predictions],
    }
    return record, encoded.tobytes()


def _response_record(record: dict, rendered_bytes: bytes) -> dict:
    return {
        **record,
        "image_jpeg_base64": base64.b64encode(rendered_bytes).decode("ascii"),
        "saved_files": None,
    }


@app.post("/api/batch")
async def predict_batch(
    images: list[UploadFile] = File(...),
    mode: Literal["face", "person", "both"] = Form("both"),
    save_result: bool = Form(False),
) -> dict:
    if not images:
        raise HTTPException(status_code=400, detail="Select at least one image.")
    if len(images) > MAX_BATCH_IMAGES:
        raise HTTPException(
            status_code=413,
            detail=f"Batch limit is {MAX_BATCH_IMAGES} images.",
        )
    total_bytes = 0
    records = []
    response_items = []
    batch_id = uuid.uuid4().hex if save_result else None
    batch_dir = OUTPUT_DIR / "runs" / batch_id if batch_id else None

    for index, image in enumerate(images):
        raw_image = await _read_upload(image)
        total_bytes += len(raw_image)
        if total_bytes > MAX_BATCH_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Batch exceeds the {MAX_BATCH_BYTES}-byte total limit.",
            )
        record, rendered_bytes = _infer_image(raw_image, mode)
        response_item = _response_record(record, rendered_bytes)
        image_file = f"{index + 1:05d}.jpg"
        record["image_file"] = image_file
        response_item["filename"] = image.filename or image_file
        response_items.append(response_item)
        if batch_dir:
            records.append(record)
            (batch_dir / "images").mkdir(parents=True, exist_ok=True)
            source_image = cv2.imdecode(
                np.frombuffer(raw_image, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            success, source_jpeg = cv2.imencode(".jpg", source_image)
            if not success:
                raise HTTPException(
                    status_code=500, detail="Could not encode source image for export."
                )
            (batch_dir / "images" / image_file).write_bytes(source_jpeg.tobytes())

    if batch_dir and records:
        (batch_dir / "results.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return {
        "mode": mode,
        "batch_id": batch_id,
        "image_count": len(response_items),
        "results": response_items,
    }


@app.get("/api/batch/{batch_id}/export/{kind}")
def export_batch(batch_id: str, kind: Literal["face", "person"]) -> Response:
    if not re.fullmatch(r"[a-f0-9]{32}", batch_id):
        raise HTTPException(status_code=400, detail="Invalid batch ID.")
    run_dir = OUTPUT_DIR / "runs" / batch_id
    try:
        archive = build_coco_keypoints_zip(run_dir, kind, engine.schemas[kind])
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{kind}_keypoints.zip"'
        },
    )
