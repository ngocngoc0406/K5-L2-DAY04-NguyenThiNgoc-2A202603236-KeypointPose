import io
import json
import zipfile

import cv2
import numpy as np
from fastapi.testclient import TestClient

from pose_landmark_system.app import main
from pose_landmark_system.app.inference import Keypoint, Prediction


def test_batch_saves_and_exports_separate_face_coco(monkeypatch, tmp_path):
    schema = main.engine.schemas["face"]
    prediction = Prediction(
        kind="face",
        confidence=0.9,
        bbox=(2, 2, 18, 18),
        keypoints=tuple(
            Keypoint(
                name=name,
                x=10.0,
                y=10.0,
                confidence=0.1 if index == 0 else 0.9,
            )
            for index, name in enumerate(schema.keypoints)
        ),
    )
    person_schema = main.engine.schemas["person"]
    person_prediction = Prediction(
        kind="person",
        confidence=0.8,
        bbox=(1, 1, 19, 19),
        keypoints=tuple(
            Keypoint(name=name, x=9.0, y=9.0, confidence=0.8)
            for name in person_schema.keypoints
        ),
    )
    monkeypatch.setattr(
        main.engine,
        "predict",
        lambda _image, _mode: [prediction, person_prediction],
    )
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
    success, image = cv2.imencode(".jpg", np.zeros((20, 20, 3), dtype=np.uint8))
    assert success

    with TestClient(main.app) as client:
        response = client.post(
            "/api/batch",
            files=[
                ("images", ("one.jpg", image.tobytes(), "image/jpeg")),
                ("images", ("two.jpg", image.tobytes(), "image/jpeg")),
            ],
            data={"mode": "both", "save_result": "true"},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["image_count"] == 2
        assert result["batch_id"]

        export = client.get(
            f"/api/batch/{result['batch_id']}/export/face"
        )
        person_export = client.get(
            f"/api/batch/{result['batch_id']}/export/person"
        )

    assert export.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        coco = json.loads(archive.read("annotations/face_keypoints_default.json"))
        assert len(coco["images"]) == 2
        assert len(coco["annotations"]) == 2
        assert len(coco["annotations"][0]["keypoints"]) == 39
        assert coco["annotations"][0]["num_keypoints"] == 12
        assert coco["annotations"][0]["keypoints"][:3] == [0, 0, 0]
        assert "images/00001.jpg" in archive.namelist()
    assert person_export.status_code == 200
    with zipfile.ZipFile(io.BytesIO(person_export.content)) as archive:
        coco = json.loads(archive.read("annotations/person_keypoints_default.json"))
        assert len(coco["annotations"][0]["keypoints"]) == 51
        assert coco["categories"][0]["keypoints"][0] == "nose"
