# Downloads stay inside this project; no installers or PATH changes.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskTools = Join-Path $taskRoot 'tools'
$taskDownloads = Join-Path $taskTools 'downloads'
New-Item -ItemType Directory -Force -Path $taskDownloads | Out-Null
$taskSfinderUrl = 'https://github.com/knewjade/solution-finder/releases/download/v1.43/solution-finder-1.43.zip'
$taskSfinderZip = Join-Path $taskDownloads 'solution-finder-1.43.zip'
if (-not (Test-Path -LiteralPath (Join-Path $taskTools 'solution-finder\sfinder.jar'))) {
    Invoke-WebRequest -Uri $taskSfinderUrl -OutFile $taskSfinderZip
    Expand-Archive -LiteralPath $taskSfinderZip -DestinationPath (Join-Path $taskTools 'solution-finder') -Force
    Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/knewjade/solution-finder/v1.43/LICENSE' -OutFile (Join-Path $taskTools 'solution-finder\LICENSE')
}
if (-not (Get-ChildItem (Join-Path $taskTools 'java') -Filter java.exe -Recurse -ErrorAction SilentlyContinue)) {
    $taskJavaAsset = Invoke-RestMethod -Uri 'https://api.adoptium.net/v3/assets/latest/17/hotspot?architecture=x64&image_type=jre&os=windows&vendor=eclipse'
    $taskJavaPackage = $taskJavaAsset[0].binary.package
    $taskJavaPackage | Select-Object name,link,checksum,size | ConvertTo-Json | Set-Content (Join-Path $taskDownloads 'java-source.json')
    $taskJavaZip = Join-Path $taskDownloads 'java.zip'
    Invoke-WebRequest -Uri $taskJavaPackage.link -OutFile $taskJavaZip
    if ((Get-FileHash -LiteralPath $taskJavaZip -Algorithm SHA256).Hash.ToLower() -ne $taskJavaPackage.checksum) { throw 'Java checksum mismatch.' }
    Expand-Archive -LiteralPath $taskJavaZip -DestinationPath (Join-Path $taskTools 'java') -Force
}
& (Join-Path $PSScriptRoot 'build-bridge.ps1')
Write-Output 'PC solver dependencies are ready.'
