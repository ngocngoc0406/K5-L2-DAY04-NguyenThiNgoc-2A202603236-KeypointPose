$ErrorActionPreference = "Stop"
$modelDir = Join-Path $PSScriptRoot "..\models"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

$models = @(
    @{
        Url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
        Path = Join-Path $modelDir "blaze_face_short_range.tflite"
    },
    @{
        Url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
        Path = Join-Path $modelDir "face_landmarker.task"
    }
)

foreach ($model in $models) {
    if (-not (Test-Path $model.Path)) {
        Invoke-WebRequest -Uri $model.Url -OutFile $model.Path
    }
    if ((Get-Item $model.Path).Length -eq 0) {
        throw "Downloaded model file is empty: $($model.Path)"
    }
    Write-Output "Ready: $($model.Path)"
}
