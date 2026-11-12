from __future__ import annotations

import json
import os
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_ROOT = REPOSITORY_ROOT / "pose_landmark_system"
SCHEMA_PATH = REPOSITORY_ROOT / "src" / "keypoint_schema.json"

NODE_POSITIONS = {
    "person": [
        (50, 9), (53, 7), (47, 7), (57, 9), (43, 9), (64, 22), (36, 22),
        (70, 38), (30, 38), (73, 53), (27, 53), (58, 52), (42, 52),
        (60, 73), (40, 73), (61, 94), (39, 94),
    ],
    "face": [
        (80, 26), (58, 26), (69, 21), (69, 31), (15, 26), (37, 26),
        (26, 21), (26, 31), (48, 59), (64, 82), (31, 82), (48, 79), (48, 88),
    ],
}


def build_label(kind: str, definition: dict) -> dict:
    keypoints = definition["keypoints"]
    positions = NODE_POSITIONS[kind]
    svg_lines = [
        (
            f'<line x1="{positions[left - 1][0]}" y1="{positions[left - 1][1]}" '
            f'x2="{positions[right - 1][0]}" y2="{positions[right - 1][1]}" '
            f'data-type="edge" data-node-from="{left}" data-node-to="{right}"></line>'
        )
        for left, right in definition["skeleton"]
    ]
    svg_nodes = [
        (
            f'<circle r="1" cx="{x}" cy="{y}" data-type="element node" '
            f'data-element-id="{index}" data-node-id="{index}" '
            f'data-label-name="{name}"></circle>'
        )
        for index, (name, (x, y)) in enumerate(zip(keypoints, positions), start=1)
    ]
    return {
        "name": kind,
        "type": "skeleton",
        "svg": "\n".join(svg_lines + svg_nodes),
        "sublabels": [
            {"id": index, "name": name, "type": "points"}
            for index, name in enumerate(keypoints)
        ],
    }


def main() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for kind in ("person", "face"):
        template_path = SYSTEM_ROOT / "nuclio" / kind / "function.yaml.template"
        function_path = template_path.with_name("function.yaml")
        template = template_path.read_text(encoding="utf-8")
        if template.count("__CVAT_SPEC__") != 1:
            raise ValueError(f"Expected one CVAT schema placeholder in {template_path}")
        template = template.replace(
            "__MMPPOSE_URL__",
            os.environ.get("CVAT_MMPPOSE_URL", "http://172.17.0.3:8080"),
        )
        spec = json.dumps([build_label(kind, schema[kind])], ensure_ascii=False, indent=2)
        spec_block = "|\n" + "\n".join(f"      {line}" for line in spec.splitlines())
        function_path.write_text(
            template.replace("__CVAT_SPEC__", spec_block), encoding="utf-8"
        )
        print(f"Generated {function_path}")


if __name__ == "__main__":
    main()
