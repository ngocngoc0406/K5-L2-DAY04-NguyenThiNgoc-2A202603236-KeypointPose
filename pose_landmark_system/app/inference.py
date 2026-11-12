from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from .schema import APP_ROOT, KeypointSchema, load_schemas


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

COCO_PERSON_KEYPOINTS = (
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


@dataclass(frozen=True)
class Keypoint:
    name: str
    x: float
    y: float
    confidence: float


@dataclass(frozen=True)
class Prediction:
    kind: str
    confidence: float
    bbox: tuple[int, int, int, int]
    keypoints: tuple[Keypoint, ...]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["bbox"] = list(self.bbox)
        result["keypoints"] = [asdict(point) for point in self.keypoints]
        return result


def _asset_path(env_name: str, default: str) -> Path:
    path = Path(os.environ.get(env_name, default)).expanduser()
    if not path.is_absolute():
        path = (APP_ROOT / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Model asset not found: {path}. See the model setup section in README.md."
        )
    return path


class InferenceEngine:
    def __init__(self) -> None:
        self.schemas = load_schemas()
        self._face_detector = None
        self._face_landmarker = None
        self._pose_model = None
        self._face_lock = threading.Lock()
        self._pose_lock = threading.Lock()

    def predict(self, image_bgr: np.ndarray, mode: str) -> list[Prediction]:
        if mode not in {"face", "person", "both"}:
            raise ValueError("mode must be one of: face, person, both")
        predictions: list[Prediction] = []
        if mode in {"face", "both"}:
            predictions.extend(self._predict_faces(image_bgr))
        if mode in {"person", "both"}:
            predictions.extend(self._predict_people(image_bgr))
        return predictions

    def _load_face_models(self) -> None:
        if self._face_detector is not None and self._face_landmarker is not None:
            return
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            raise ImportError(
                "Face inference requires the 'mediapipe' dependency."
            ) from error

        detector_path = _asset_path(
            "FACE_DETECTOR_MODEL", "models/blaze_face_short_range.tflite"
        )
        landmarker_path = _asset_path(
            "FACE_LANDMARKER_MODEL", "models/face_landmarker.task"
        )
        detector_options = vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(detector_path)),
            min_detection_confidence=0.5,
        )
        landmarker_options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(landmarker_path)),
            num_faces=20,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._face_detector = vision.FaceDetector.create_from_options(
            detector_options
        )
        self._face_landmarker = vision.FaceLandmarker.create_from_options(
            landmarker_options
        )
        self._mp = mp

    def _predict_faces(self, image_bgr: np.ndarray) -> list[Prediction]:
        with self._face_lock:
            self._load_face_models()
            image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            mp_image = self._mp.Image(
                image_format=self._mp.ImageFormat.SRGB, data=image_rgb
            )
            result = self._face_detector.detect(mp_image)
            height, width = image_bgr.shape[:2]
            predictions = []
            for detection in result.detections:
                box = detection.bounding_box
                left = max(0, box.origin_x)
                top = max(0, box.origin_y)
                right = min(width, box.origin_x + box.width)
                bottom = min(height, box.origin_y + box.height)
                pad_x = max(1, int((right - left) * 0.18))
                pad_y = max(1, int((bottom - top) * 0.18))
                x0 = max(0, left - pad_x)
                y0 = max(0, top - pad_y)
                x1 = min(width, right + pad_x)
                y1 = min(height, bottom + pad_y)
                if x1 <= x0 or y1 <= y0:
                    continue

                crop_rgb = image_rgb[y0:y1, x0:x1]
                crop = self._mp.Image(
                    image_format=self._mp.ImageFormat.SRGB, data=crop_rgb
                )
                landmark_result = self._face_landmarker.detect(crop)
                if not landmark_result.face_landmarks:
                    continue
                landmarks = landmark_result.face_landmarks[0]
                confidence = (
                    float(detection.categories[0].score)
                    if detection.categories
                    else 0.0
                )
                points = []
                for name in self.schemas["face"].keypoints:
                    landmark = landmarks[FACE_MESH_INDICES[name]]
                    points.append(
                        Keypoint(
                            name=name,
                            x=float(x0 + landmark.x * (x1 - x0)),
                            y=float(y0 + landmark.y * (y1 - y0)),
                            confidence=confidence,
                        )
                    )
                predictions.append(
                    Prediction(
                        kind="face",
                        confidence=confidence,
                        bbox=(left, top, right, bottom),
                        keypoints=tuple(points),
                    )
                )
            return predictions

    def _predict_people(self, image_bgr: np.ndarray) -> list[Prediction]:
        with self._pose_lock:
            if self._pose_model is None:
                try:
                    from ultralytics import YOLO
                except ImportError as error:
                    raise ImportError(
                        "Person inference requires the 'ultralytics' dependency."
                    ) from error
                model_path = os.environ.get(
                    "PERSON_POSE_MODEL", "yolo11n-pose.pt"
                )
                self._pose_model = YOLO(model_path)

            results = self._pose_model.predict(
                source=image_bgr, conf=0.25, verbose=False
            )
            predictions: list[Prediction] = []
            for result in results:
                if result.keypoints is None or result.boxes is None:
                    continue
                coordinates = result.keypoints.xy.cpu().numpy()
                point_scores = (
                    result.keypoints.conf.cpu().numpy()
                    if result.keypoints.conf is not None
                    else None
                )
                boxes = result.boxes.xyxy.cpu().numpy()
                box_scores = result.boxes.conf.cpu().numpy()
                classes = result.boxes.cls.cpu().numpy()
                for index, (box, box_score, class_id) in enumerate(
                    zip(boxes, box_scores, classes)
                ):
                    if int(class_id) != 0:
                        continue
                    points = []
                    for point_index, name in enumerate(COCO_PERSON_KEYPOINTS):
                        score = (
                            float(point_scores[index][point_index])
                            if point_scores is not None
                            else float(box_score)
                        )
                        points.append(
                            Keypoint(
                                name=name,
                                x=float(coordinates[index][point_index][0]),
                                y=float(coordinates[index][point_index][1]),
                                confidence=score,
                            )
                        )
                    predictions.append(
                        Prediction(
                            kind="person",
                            confidence=float(box_score),
                            bbox=tuple(int(value) for value in box),
                            keypoints=tuple(points),
                        )
                    )
            return predictions

    def close(self) -> None:
        if self._face_detector is not None:
            self._face_detector.close()
            self._face_detector = None
        if self._face_landmarker is not None:
            self._face_landmarker.close()
            self._face_landmarker = None


def get_keypoint_schema(kind: str, schemas: dict[str, KeypointSchema]):
    return schemas[kind]
