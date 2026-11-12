import json

import pytest

from pose_landmark_system.app.schema import APP_ROOT, load_schemas
from pose_landmark_system.roboflow_upload import _load_manifest, _resolve_env_path


def test_manifest_rejects_mixing_face_and_person(tmp_path):
    (tmp_path / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "task": "person",
                "source": "COCO",
                "license": "verified terms",
                "keypoints": list(load_schemas()["person"].keypoints),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "train").mkdir()

    with pytest.raises(ValueError, match="expected 'face'"):
        _load_manifest(tmp_path, "face")


def test_dataset_path_rejects_lab_data(monkeypatch):
    lab_images = APP_ROOT.parent / "src" / "lab" / "images"
    monkeypatch.setenv("FACE_DATASET_DIR", str(lab_images))

    with pytest.raises(ValueError, match="outside the repository"):
        _resolve_env_path("FACE_DATASET_DIR")
