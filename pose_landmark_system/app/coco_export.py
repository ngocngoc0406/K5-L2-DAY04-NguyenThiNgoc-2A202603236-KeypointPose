from __future__ import annotations

import io
import json
import math
import zipfile
from pathlib import Path

from .schema import KeypointSchema


CONFIDENCE_THRESHOLD = 0.2


def build_coco_keypoints_zip(
    run_dir: Path, kind: str, schema: KeypointSchema
) -> bytes:
    results_path = run_dir / "results.json"
    if not results_path.is_file():
        raise FileNotFoundError(f"Saved batch not found: {run_dir.name}")
    records = json.loads(results_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Saved batch results must be a list.")

    images = []
    annotations = []
    image_id = 1
    annotation_id = 1
    for record in records:
        image_path = run_dir / "images" / record["image_file"]
        if not image_path.is_file():
            raise ValueError(f"Saved batch image is missing: {record['image_file']}")
        width = int(record["image_width"])
        height = int(record["image_height"])
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid image dimensions: {record['image_file']}")
        images.append(
            {
                "id": image_id,
                "file_name": f"images/{record['image_file']}",
                "width": width,
                "height": height,
            }
        )

        for prediction in record["predictions"]:
            if prediction.get("kind") != kind:
                continue
            points_by_name = {
                point.get("name"): point for point in prediction.get("keypoints", [])
            }
            if set(points_by_name) != set(schema.keypoints):
                raise ValueError(
                    f"Prediction keypoints do not match the {kind} schema."
                )
            flat_points = []
            visible_count = 0
            for name in schema.keypoints:
                point = points_by_name[name]
                x = float(point["x"])
                y = float(point["y"])
                confidence = float(point["confidence"])
                if not all(math.isfinite(value) for value in (x, y, confidence)):
                    raise ValueError(f"Non-finite {kind} keypoint: {name}")
                visible = (
                    confidence >= CONFIDENCE_THRESHOLD
                    and 0 <= x < width
                    and 0 <= y < height
                )
                if visible:
                    flat_points.extend([round(x, 3), round(y, 3), 2])
                    visible_count += 1
                else:
                    flat_points.extend([0, 0, 0])

            x0, y0, x1, y1 = (float(value) for value in prediction["bbox"])
            x0 = min(max(x0, 0), width)
            y0 = min(max(y0, 0), height)
            x1 = min(max(x1, x0), width)
            y1 = min(max(y1, y0), height)
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": 1,
                    "keypoints": flat_points,
                    "num_keypoints": visible_count,
                    "bbox": [round(x0, 3), round(y0, 3), round(x1 - x0, 3), round(y1 - y0, 3)],
                    "area": round((x1 - x0) * (y1 - y0), 3),
                    "iscrowd": 0,
                    "score": float(prediction["confidence"]),
                }
            )
            annotation_id += 1
        image_id += 1

    if not images:
        raise ValueError("Saved batch contains no images.")
    coco = {
        "info": {
            "description": f"Auto-annotation predictions ({kind}); review before use.",
            "visibility_policy": (
                "v=2 when confidence >= 0.2 and point is in frame; otherwise v=0. "
                "The model does not infer occlusion, so v=1 is not generated."
            ),
        },
        "images": images,
        "annotations": annotations,
        "categories": [
            {
                "id": 1,
                "name": kind,
                "keypoints": list(schema.keypoints),
                "skeleton": [list(edge) for edge in schema.skeleton],
            }
        ],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"annotations/{kind}_keypoints_default.json",
            json.dumps(coco, ensure_ascii=False, indent=2),
        )
        for record in records:
            image_path = run_dir / "images" / record["image_file"]
            archive.write(image_path, f"images/{record['image_file']}")
    return buffer.getvalue()
