import base64
import json
import os

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import numpy as np


FACE_MESH_INDICES = {
    "left_eye_outer": 263,
    "left_eye_inner": 362,
    "left_eye_upper": 386,
    "left_eye_lower": 374,
    "right_eye_outer": 33,
    "right_eye_inner": 133,
    "right_eye_upper": 159,
    "right_eye_lower": 145,
    "nose_tip": 1,
    "mouth_left": 291,
    "mouth_right": 61,
    "lip_upper": 13,
    "lip_lower": 14,
}


def _request_data(body):
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    if isinstance(body, str):
        body = json.loads(body)
    return body


def init_context(context):
    assets = os.environ.get("FACE_MODEL_DIR", "/opt/nuclio/assets")
    detector_path = os.path.join(assets, "blaze_face_short_range.tflite")
    landmarker_path = os.path.join(assets, "face_landmarker.task")
    context.logger.info("Loading MediaPipe face models")
    context.user_data.detector = vision.FaceDetector.create_from_options(
        vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=detector_path),
            min_detection_confidence=0.5,
        )
    )
    context.user_data.landmarker = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=landmarker_path),
            num_faces=20,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
    )
    context.user_data.mp = mp
    context.logger.info("MediaPipe face models loaded")


def _face_skeleton(image_rgb, detection, landmarker, threshold, mp_module):
    height, width = image_rgb.shape[:2]
    box = detection.bounding_box
    left = max(0, box.origin_x)
    top = max(0, box.origin_y)
    right = min(width, box.origin_x + box.width)
    bottom = min(height, box.origin_y + box.height)
    if right <= left or bottom <= top:
        return None

    pad_x = max(1, int((right - left) * 0.18))
    pad_y = max(1, int((bottom - top) * 0.18))
    x0 = max(0, left - pad_x)
    y0 = max(0, top - pad_y)
    x1 = min(width, right + pad_x)
    y1 = min(height, bottom + pad_y)
    crop = np.ascontiguousarray(image_rgb[y0:y1, x0:x1])
    mp_image = mp_module.Image(
        image_format=mp_module.ImageFormat.SRGB, data=crop
    )
    result = landmarker.detect(mp_image)
    if not result.face_landmarks:
        return None

    confidence = (
        float(detection.categories[0].score) if detection.categories else 0.0
    )
    landmarks = result.face_landmarks[0]
    elements = []
    for name, landmark_index in FACE_MESH_INDICES.items():
        landmark = landmarks[landmark_index]
        x = float(x0 + landmark.x * (x1 - x0))
        y = float(y0 + landmark.y * (y1 - y0))
        outside = confidence < threshold or not (0 <= x < width and 0 <= y < height)
        elements.append(
            {
                "label": name,
                "type": "points",
                "outside": int(outside),
                "points": [x, y],
                "confidence": str(confidence),
            }
        )
    return {
        "confidence": str(confidence),
        "label": "face",
        "type": "skeleton",
        "elements": elements,
    }


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
        encoded = base64.b64decode(data["image"], validate=True)
    except (ValueError, TypeError):
        return context.Response(
            body=json.dumps({"error": "Image must be valid base64."}),
            headers={},
            content_type="application/json",
            status_code=400,
        )

    image_bgr = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image_bgr is None:
        return context.Response(
            body=json.dumps({"error": "Image payload could not be decoded."}),
            headers={},
            content_type="application/json",
            status_code=415,
        )
    threshold = float(data.get("threshold", 0.5))
    if not 0 <= threshold <= 1:
        return context.Response(
            body=json.dumps({"error": "threshold must be between 0 and 1."}),
            headers={},
            content_type="application/json",
            status_code=400,
        )

    image_rgb = np.ascontiguousarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    mp_image = context.user_data.mp.Image(
        image_format=context.user_data.mp.ImageFormat.SRGB, data=image_rgb
    )
    detections = context.user_data.detector.detect(mp_image).detections
    results = []
    for detection in detections:
        skeleton = _face_skeleton(
            image_rgb,
            detection,
            context.user_data.landmarker,
            threshold,
            context.user_data.mp,
        )
        if skeleton is not None:
            results.append(skeleton)
    return context.Response(
        body=json.dumps(results),
        headers={},
        content_type="application/json",
        status_code=200,
    )
