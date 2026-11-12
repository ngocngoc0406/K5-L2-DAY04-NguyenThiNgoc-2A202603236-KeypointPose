from __future__ import annotations

import cv2
import numpy as np

from .inference import Prediction
from .schema import KeypointSchema


COLORS = {
    "face": (255, 190, 30),
    "person": (70, 220, 100),
}
CONFIDENCE_THRESHOLD = 0.2


def render_predictions(
    image_bgr: np.ndarray,
    predictions: list[Prediction],
    schemas: dict[str, KeypointSchema],
) -> np.ndarray:
    rendered = image_bgr.copy()
    height, width = rendered.shape[:2]
    for prediction in predictions:
        color = COLORS[prediction.kind]
        x0, y0, x1, y1 = prediction.bbox
        cv2.rectangle(
            rendered,
            (max(0, x0), max(0, y0)),
            (min(width - 1, x1), min(height - 1, y1)),
            color,
            2,
            cv2.LINE_AA,
        )
        label = f"{prediction.kind} {prediction.confidence:.2f}"
        cv2.putText(
            rendered,
            label,
            (max(0, x0), max(18, y0 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

        for start, end in schemas[prediction.kind].skeleton:
            point_a = prediction.keypoints[start]
            point_b = prediction.keypoints[end]
            if (
                point_a.confidence >= CONFIDENCE_THRESHOLD
                and point_b.confidence >= CONFIDENCE_THRESHOLD
            ):
                cv2.line(
                    rendered,
                    (int(round(point_a.x)), int(round(point_a.y))),
                    (int(round(point_b.x)), int(round(point_b.y))),
                    color,
                    2,
                    cv2.LINE_AA,
                )

        for point in prediction.keypoints:
            if point.confidence >= CONFIDENCE_THRESHOLD:
                cv2.circle(
                    rendered,
                    (int(round(point.x)), int(round(point.y))),
                    3 if prediction.kind == "face" else 4,
                    color,
                    -1,
                    cv2.LINE_AA,
                )
    return rendered
