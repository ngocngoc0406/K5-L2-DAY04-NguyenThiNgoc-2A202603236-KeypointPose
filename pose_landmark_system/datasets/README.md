# Dataset boundaries and Roboflow setup

Keep two independent dataset roots:

```text
<external-data-root>\
  face\
    train\
    valid\
    test\
    dataset_manifest.json
  person\
    train\
    valid\
    test\
    dataset_manifest.json
```

The roots must be outside this repository's `data/`, `src/lab/images/`, and
`src/exports/`. Never use the lab assignment data or model predictions as
ground-truth annotations.

## Dataset candidates

- **Person:** COCO Keypoints; keep its 17 COCO keypoints and visibility values.
  Obtain the official dataset and check its terms for the intended use.
- **Face:** evaluate a public facial-landmark dataset with 68 or more landmarks
  (for example 300W or WFLW). Before use, verify the specific image/annotation
  license and build a reviewed mapping to the lab's 13 names. Do not assume a
  landmark-index mapping from a model or another schema.

Do not upload a dataset until its source, license, split, label ordering, and
mapping have been reviewed. The uploader checks manifest metadata and exact
keypoint order; it does not convert annotation formats or infer labels.

Example `dataset_manifest.json` for face data:

```json
{
  "task": "face",
  "annotation_format": "coco-keypoints",
  "source": "Dataset name and official URL",
  "license": "Exact license/terms verified for these files",
  "keypoints": [
    "left_eye_outer", "left_eye_inner", "left_eye_upper", "left_eye_lower",
    "right_eye_outer", "right_eye_inner", "right_eye_upper", "right_eye_lower",
    "nose_tip", "mouth_left", "mouth_right", "lip_upper", "lip_lower"
  ]
}
```

For person data set `"task": "person"` and copy the ordered 17 names from
`src/keypoint_schema.json`. Provide `_annotations.coco.json` in each populated
split; this script verifies the category and keypoint order but does not
transform annotation JSON.

## Create two projects

1. In Roboflow, create one **Keypoint Detection** project for `face` and another
   for `person`; do not share a project or dataset between them.
2. Select a keypoint annotation format compatible with the dataset's schema.
   The face project must define the 13 agreed landmarks; the person project
   must define COCO-17 in the exact COCO order.
3. Upload reviewed train/valid/test splits. Check several annotations in the UI,
   then create a version for each project separately. Choose a keypoint
   detection model for training each version (not a bounding-box-only detector);
   check the version preview and evaluation for the correct number and order of
   landmarks before publishing. A generic detector checkpoint cannot replace a
   keypoint model.
4. Record the workspace and the two distinct project IDs in environment
   variables. Never put the API key in source code or commit it.

Configure variables in the process environment:

```powershell
$env:ROBOFLOW_API_KEY = "<set securely in your local shell or secret manager>"
$env:ROBOFLOW_WORKSPACE = "your-workspace"
$env:ROBOFLOW_FACE_PROJECT = "your-face-project"
$env:ROBOFLOW_PERSON_PROJECT = "your-person-project"
$env:FACE_DATASET_DIR = "D:\datasets\face"
$env:PERSON_DATASET_DIR = "D:\datasets\person"
```

The uploader requires a manifest and performs a dry run by default:

```powershell
python .\roboflow_upload.py face
python .\roboflow_upload.py person
```

Review the printed destination and dataset information first. Only then add
`--confirm-upload` to upload the selected dataset:

```powershell
python .\roboflow_upload.py face --confirm-upload
python .\roboflow_upload.py person --confirm-upload
```

The script requires a per-task manifest, rejects the lab data paths and refuses
identical face/person project IDs. It uses `is_prediction=False`; generated
predictions are never presented as ground-truth labels.
