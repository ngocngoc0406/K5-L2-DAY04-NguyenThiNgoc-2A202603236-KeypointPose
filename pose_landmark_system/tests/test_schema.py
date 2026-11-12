from pathlib import Path

from pose_landmark_system.app.schema import DEFAULT_SCHEMA_PATH, load_schemas


def test_schema_matches_face_and_coco_contracts():
    schemas = load_schemas(DEFAULT_SCHEMA_PATH)

    assert len(schemas["face"].keypoints) == 13
    assert len(schemas["face"].skeleton) == 13
    assert len(schemas["person"].keypoints) == 17
    assert len(schemas["person"].skeleton) == 19
    assert schemas["person"].keypoints[0] == "nose"
    assert schemas["person"].keypoints[-1] == "right_ankle"


def test_dataset_directories_are_separate_from_lab_data():
    project_root = Path(__file__).resolve().parents[2]
    protected = (
        project_root / "data",
        project_root / "src" / "lab" / "images",
        project_root / "src" / "exports",
    )
    assert all(path.exists() for path in protected)
