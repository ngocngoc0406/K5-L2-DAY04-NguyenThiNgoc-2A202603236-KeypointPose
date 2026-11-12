import json
import os

import requests


MMPPOSE_URL = os.environ.get("CVAT_MMPPOSE_URL")
COCO17_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


def remap_body_predictions(predictions):
    results = []
    for prediction in predictions:
        if prediction.get("label") != "body" or prediction.get("type") != "skeleton":
            continue
        source_elements = {
            element.get("label"): element
            for element in prediction.get("elements", [])
        }
        missing = [
            str(index + 1)
            for index in range(len(COCO17_NAMES))
            if str(index + 1) not in source_elements
        ]
        if missing:
            raise ValueError(
                "HRNet body result is missing keypoint indices: "
                + ", ".join(missing)
            )
        elements = []
        for index, name in enumerate(COCO17_NAMES, start=1):
            source = source_elements[str(index)]
            points = source.get("points")
            if (
                source.get("type") != "points"
                or not isinstance(points, list)
                or len(points) != 2
            ):
                raise ValueError(f"HRNet returned an invalid point for index {index}")
            elements.append(
                {
                    "label": name,
                    "type": "points",
                    "outside": int(bool(source.get("outside", 0))),
                    "points": [float(points[0]), float(points[1])],
                    "confidence": str(source.get("confidence", "0")),
                }
            )
        results.append(
            {
                "confidence": str(prediction.get("confidence", "0")),
                "label": "person",
                "type": "skeleton",
                "elements": elements,
            }
        )
    return results


def init_context(context):
    if not MMPPOSE_URL:
        raise RuntimeError("CVAT_MMPPOSE_URL must target the deployed HRNet32 function.")
    context.user_data.source_url = MMPPOSE_URL.rstrip("/")


def _request_data(body):
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    if isinstance(body, str):
        body = json.loads(body)
    return body


def handler(context, event):
    try:
        data = _request_data(event.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if not isinstance(data, dict) or not data.get("image"):
        return context.Response(
            body=json.dumps({"error": "Expected base64 image in request body."}),
            headers={},
            content_type="application/json",
            status_code=400,
        )

    try:
        response = requests.post(
            context.user_data.source_url,
            headers={"Content-Type": "application/json"},
            json={
                "image": data["image"],
                "threshold": data.get("threshold", 0.55),
            },
            timeout=(5, 120),
        )
        response.raise_for_status()
        predictions = response.json()
        if not isinstance(predictions, list):
            raise ValueError("HRNet response must be a JSON array.")
        results = remap_body_predictions(predictions)
    except requests.RequestException as error:
        context.logger.error("HRNet Nuclio invocation failed: %s", error)
        return context.Response(
            body=json.dumps({"error": "HRNet invocation failed."}),
            headers={},
            content_type="application/json",
            status_code=502,
        )
    except (ValueError, TypeError, KeyError) as error:
        context.logger.error("Invalid HRNet response: %s", error)
        return context.Response(
            body=json.dumps({"error": str(error)}),
            headers={},
            content_type="application/json",
            status_code=502,
        )

    return context.Response(
        body=json.dumps(results),
        headers={},
        content_type="application/json",
        status_code=200,
    )
