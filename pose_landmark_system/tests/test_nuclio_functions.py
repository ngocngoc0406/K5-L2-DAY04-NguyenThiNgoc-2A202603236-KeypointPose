import importlib.util
import json
from pathlib import Path

import yaml

from pose_landmark_system.app.schema import APP_ROOT, load_schemas
from pose_landmark_system.scripts.generate_nuclio_specs import build_label


ROOT = APP_ROOT / "nuclio"


def _load_person_function():
    path = ROOT / "person" / "main.py"
    spec = importlib.util.spec_from_file_location("person_nuclio_function", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_person_adapter_maps_hrnet_indices_to_coco_names():
    module = _load_person_function()
    body = {
        "label": "body",
        "type": "skeleton",
        "confidence": "0.91",
        "elements": [
            {
                "label": str(index + 1),
                "type": "points",
                "outside": 0,
                "points": [float(index), float(index + 1)],
                "confidence": "0.8",
            }
            for index in range(17)
        ],
    }

    result = module.remap_body_predictions([body, {"label": "face"}])

    assert len(result) == 1
    assert result[0]["label"] == "person"
    assert [point["label"] for point in result[0]["elements"]] == list(
        load_schemas()["person"].keypoints
    )
    assert result[0]["elements"][0]["points"] == [0.0, 1.0]


def test_generated_function_specs_match_existing_schema():
    schemas = load_schemas()
    for kind in ("face", "person"):
        label = build_label(kind, json.loads(
            (APP_ROOT.parent / "src" / "keypoint_schema.json").read_text(
                encoding="utf-8"
            )
        )[kind])
        assert [node["name"] for node in label["sublabels"]] == list(
            schemas[kind].keypoints
        )
        manifest = yaml.safe_load(
            (ROOT / kind / "function.yaml").read_text(encoding="utf-8")
        )
        model_spec = json.loads(manifest["metadata"]["annotations"]["spec"])
        assert model_spec == [label]
        assert manifest["spec"]["runtime"] == "python:3.10"
