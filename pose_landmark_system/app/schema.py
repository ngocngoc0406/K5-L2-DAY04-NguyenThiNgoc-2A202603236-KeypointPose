from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = APP_ROOT.parent
DEFAULT_SCHEMA_PATH = REPOSITORY_ROOT / "src" / "keypoint_schema.json"


@dataclass(frozen=True)
class KeypointSchema:
    keypoints: tuple[str, ...]
    skeleton: tuple[tuple[int, int], ...]


def load_schemas(path: str | Path | None = None) -> dict[str, KeypointSchema]:
    schema_path = Path(
        path or os.environ.get("KEYPOINT_SCHEMA_PATH") or DEFAULT_SCHEMA_PATH
    ).expanduser()
    if not schema_path.is_absolute():
        schema_path = (APP_ROOT / schema_path).resolve()
    if not schema_path.is_file():
        raise FileNotFoundError(f"Keypoint schema not found: {schema_path}")

    with schema_path.open(encoding="utf-8") as file:
        source: dict[str, Any] = json.load(file)

    result: dict[str, KeypointSchema] = {}
    for kind, expected_count in (("face", 13), ("person", 17)):
        category = source.get(kind)
        if not isinstance(category, dict):
            raise ValueError(f"Missing '{kind}' category in {schema_path}")
        keypoints = category.get("keypoints")
        skeleton = category.get("skeleton")
        if not isinstance(keypoints, list) or len(keypoints) != expected_count:
            raise ValueError(
                f"'{kind}' must contain exactly {expected_count} keypoints"
            )
        if not all(isinstance(name, str) and name for name in keypoints):
            raise ValueError(f"'{kind}' contains an invalid keypoint name")
        if not isinstance(skeleton, list) or not skeleton:
            raise ValueError(f"'{kind}' must contain skeleton edges")
        edges: list[tuple[int, int]] = []
        for edge in skeleton:
            if (
                not isinstance(edge, list)
                or len(edge) != 2
                or not all(isinstance(index, int) for index in edge)
                or not all(1 <= index <= expected_count for index in edge)
            ):
                raise ValueError(f"'{kind}' contains an invalid skeleton edge")
            edges.append((edge[0] - 1, edge[1] - 1))
        result[kind] = KeypointSchema(tuple(keypoints), tuple(edges))
    return result
