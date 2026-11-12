import cv2
import numpy as np
from fastapi.testclient import TestClient

from pose_landmark_system.app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_rejects_non_image_upload():
    with TestClient(app) as client:
        response = client.post(
            "/api/predict",
            files={"image": ("not-image.jpg", b"not an image", "image/jpeg")},
            data={"mode": "both"},
        )
    assert response.status_code == 415


def test_predict_rejects_unknown_mode():
    with TestClient(app) as client:
        response = client.post(
            "/api/predict",
            files={"image": ("empty.jpg", b"", "image/jpeg")},
            data={"mode": "invalid"},
        )
    assert response.status_code == 422


def test_prediction_response_and_opt_in_saving(monkeypatch, tmp_path):
    from pose_landmark_system.app import main

    image = np.zeros((32, 32, 3), dtype=np.uint8)
    encoded, buffer = cv2.imencode(".jpg", image)
    assert encoded
    monkeypatch.setattr(main.engine, "predict", lambda _image, _mode: [])
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/predict",
            files={"image": ("sample.jpg", buffer.tobytes(), "image/jpeg")},
            data={"mode": "both", "save_result": "true"},
        )

    assert response.status_code == 200
    result = response.json()
    assert result["counts"] == {"face": 0, "person": 0}
    assert result["saved_files"]["image"].endswith(".jpg")
    assert (tmp_path / result["saved_files"]["image"]).is_file()
    assert (tmp_path / result["saved_files"]["predictions"]).is_file()
