$ErrorActionPreference = "Stop"

$systemRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$faceAssetDir = Join-Path $systemRoot "nuclio\face\assets"

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE"
    }
}

$containers = docker ps --format "{{.Names}}"
if ($LASTEXITCODE -ne 0 -or $containers -notcontains "nuclio") {
    throw "Nuclio container is not running. No deployment was attempted."
}
if ($containers -notcontains "cvat_server") {
    throw "CVAT server is not running. No deployment was attempted."
}
if ($containers -notcontains "nuclio-nuclio-pth-mmpose-hrnet32") {
    throw "Existing MMPose HRNet32 function is not running. No deployment was attempted."
}

$nuclioImage = docker inspect nuclio --format "{{.Config.Image}}"
if ($nuclioImage -notmatch "1\.16\.3") {
    throw "Expected Nuclio 1.16.3, found '$nuclioImage'. Refusing deployment."
}
$nuctlVersion = (wsl -e nuctl version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $nuctlVersion -notmatch 'Label: 1\.16\.3') {
    throw "WSL nuctl 1.16.3 is required to match the running Nuclio dashboard."
}

$mmposeIp = docker inspect nuclio-nuclio-pth-mmpose-hrnet32 `
    --format "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"
if ($LASTEXITCODE -ne 0 -or $mmposeIp -notmatch '^(\d{1,3}\.){3}\d{1,3}$') {
    throw "Could not resolve the running HRNet32 function's container IP."
}
$env:CVAT_MMPPOSE_URL = "http://" + $mmposeIp + ":8080"

python (Join-Path $PSScriptRoot "generate_nuclio_specs.py")
if ($LASTEXITCODE -ne 0) {
    throw "Could not generate CVAT label specifications."
}

& (Join-Path $PSScriptRoot "download_face_models.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Could not download MediaPipe face model assets."
}

New-Item -ItemType Directory -Force -Path $faceAssetDir | Out-Null
Copy-Item (Join-Path $systemRoot "models\blaze_face_short_range.tflite") $faceAssetDir
Copy-Item (Join-Path $systemRoot "models\face_landmarker.task") $faceAssetDir

$personPath = (wsl -e wslpath -a (Join-Path $systemRoot "nuclio\person")).Trim()
$facePath = (wsl -e wslpath -a (Join-Path $systemRoot "nuclio\face")).Trim()
if ($LASTEXITCODE -ne 0 -or !$personPath.StartsWith("/")) {
    throw "Could not resolve the Person function path in WSL."
}
if (!$facePath.StartsWith("/")) {
    throw "Could not resolve the Face function path in WSL."
}

Write-Output "Deploying person adapter (uses existing HRNet32 function)..."
Invoke-Checked "wsl" @("-e", "nuctl", "deploy", "--project-name", "cvat",
    "--path", $personPath, "--platform", "local")

Write-Output "Deploying MediaPipe Face-13 function..."
Invoke-Checked "wsl" @("-e", "nuctl", "deploy", "--project-name", "cvat",
    "--path", $facePath, "--platform", "local")

Write-Output "Checking registered Nuclio functions..."
Invoke-Checked "wsl" @("-e", "nuctl", "get", "functions", "--platform", "local")
Write-Output "Both functions deployed. Existing CVAT/Compose services were not restarted."
