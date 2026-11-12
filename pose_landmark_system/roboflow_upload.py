from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

if __package__:
    from .app.schema import APP_ROOT, DEFAULT_SCHEMA_PATH, load_schemas
else:
    from app.schema import APP_ROOT, DEFAULT_SCHEMA_PATH, load_schemas


LAB_DATA_PATHS = (
    APP_ROOT.parent / "data",
    APP_ROOT.parent / "src" / "lab" / "images",
    APP_ROOT.parent / "src" / "exports",
)


def _resolve_env_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Required environment variable is missing: {name}")
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"{name} must point to an existing dataset directory: {path}")
    repository_root = APP_ROOT.parent.resolve()
    if path == repository_root or repository_root in path.parents:
        raise ValueError(
            f"Dataset must be stored outside the repository: {path}"
        )
    for protected in LAB_DATA_PATHS:
        protected = protected.resolve()
        if path == protected or protected in path.parents:
            raise ValueError(
                f"Refusing to upload lab data from a protected path: {path}"
            )
    return path


def _load_manifest(dataset_dir: Path, kind: str) -> dict:
    manifest_path = dataset_dir / "dataset_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            f"Missing {manifest_path}. See datasets/README.md for the required "
            "dataset manifest and keypoint order."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("task") != kind:
        raise ValueError(
            f"Dataset task is {manifest.get('task')!r}; expected {kind!r}. "
            "Face and person projects cannot share a dataset."
        )
    if manifest.get("annotation_format") != "coco-keypoints":
        raise ValueError(
            "Only reviewed COCO Keypoints datasets are accepted; set "
            "'annotation_format' to 'coco-keypoints' after verifying the files."
        )
    schema = load_schemas()[kind]
    if manifest.get("keypoints") != list(schema.keypoints):
        raise ValueError(
            f"Dataset keypoint order does not match the {kind} schema in "
            f"{DEFAULT_SCHEMA_PATH}"
        )
    if not manifest.get("source") or not manifest.get("license"):
        raise ValueError("Dataset manifest must include source and license.")
    split_dirs = [
        dataset_dir / split
        for split in ("train", "valid", "test")
        if (dataset_dir / split).is_dir()
    ]
    if not split_dirs:
        raise ValueError("Dataset must contain at least one train/valid/test split.")
    for split_dir in split_dirs:
        annotation_path = split_dir / "_annotations.coco.json"
        if not annotation_path.is_file():
            raise ValueError(f"Missing COCO Keypoints annotations: {annotation_path}")
        source = json.loads(annotation_path.read_text(encoding="utf-8"))
        categories = source.get("categories")
        if not isinstance(categories, list) or len(categories) != 1:
            raise ValueError(
                f"{annotation_path} must contain exactly one category; "
                "face and person labels must not be mixed."
            )
        category = categories[0]
        if category.get("name") != kind:
            raise ValueError(
                f"{annotation_path} category must be named '{kind}', "
                f"not {category.get('name')!r}."
            )
        if category.get("keypoints") != list(schema.keypoints):
            raise ValueError(
                f"{annotation_path} keypoint order does not match the {kind} schema."
            )
        category_id = category.get("id")
        annotations = source.get("annotations")
        if not isinstance(annotations, list):
            raise ValueError(f"{annotation_path} must contain an annotations list.")
        expected_length = len(schema.keypoints) * 3
        for annotation in annotations:
            if annotation.get("category_id") != category_id:
                raise ValueError(
                    f"{annotation_path} contains an annotation from another category."
                )
            points = annotation.get("keypoints")
            if not isinstance(points, list) or len(points) != expected_length:
                raise ValueError(
                    f"{annotation_path} annotations must have {expected_length} "
                    f"keypoint values for {kind}."
                )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload one isolated keypoint dataset to its Roboflow project."
    )
    parser.add_argument("kind", choices=("face", "person"))
    parser.add_argument(
        "--confirm-upload",
        action="store_true",
        help="Perform the external upload. Without this flag, only validate and preview.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ROBOFLOW_API_KEY")
    workspace_id = os.environ.get("ROBOFLOW_WORKSPACE")
    project_id = os.environ.get(f"ROBOFLOW_{args.kind.upper()}_PROJECT")
    if not api_key or not workspace_id or not project_id:
        raise ValueError(
            "Set ROBOFLOW_API_KEY, ROBOFLOW_WORKSPACE, and the matching "
            f"ROBOFLOW_{args.kind.upper()}_PROJECT environment variable."
        )
    other_project = os.environ.get(
        "ROBOFLOW_PERSON_PROJECT" if args.kind == "face" else "ROBOFLOW_FACE_PROJECT"
    )
    if other_project and project_id == other_project:
        raise ValueError("Face and person must use different Roboflow project IDs.")

    dataset_dir = _resolve_env_path(f"{args.kind.upper()}_DATASET_DIR")
    manifest = _load_manifest(dataset_dir, args.kind)
    print(
        json.dumps(
            {
                "task": args.kind,
                "dataset": str(dataset_dir),
                "workspace": workspace_id,
                "project": project_id,
                "source": manifest["source"],
                "license": manifest["license"],
                "upload_confirmed": args.confirm_upload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.confirm_upload:
        print("Dry run only. Add --confirm-upload to start the Roboflow upload.")
        return 0

    try:
        import roboflow
    except ImportError as error:
        raise RuntimeError(
            "Roboflow upload requires the optional requirements-roboflow.txt."
        ) from error

    rf = roboflow.Roboflow(api_key=api_key)
    workspace = rf.workspace(workspace_id)
    workspace.project(project_id)
    workspace.upload_dataset(
        str(dataset_dir),
        project_id,
        num_workers=4,
        project_license="Private",
        project_type="keypoint-detection",
        batch_name=f"{args.kind}-keypoints",
        num_retries=2,
        is_prediction=False,
    )
    print(f"Upload submitted to {workspace_id}/{project_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
