$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskRoot
$taskJava = (Get-ChildItem tools\java -Filter java.exe -Recurse | Select-Object -First 1).FullName
if (-not (Test-Path -LiteralPath 'tools\ecj.jar')) {
    Invoke-WebRequest -Uri 'https://repo.maven.apache.org/maven2/org/eclipse/jdt/ecj/3.38.0/ecj-3.38.0.jar' -OutFile 'tools\ecj.jar'
}
New-Item -ItemType Directory -Force -Path 'tools\bridge' | Out-Null
& $taskJava -jar tools\ecj.jar -17 -encoding UTF-8 -cp tools\solution-finder\sfinder.jar -d tools\bridge java\PcSearch.java java\GroundCandidate.java
if ($LASTEXITCODE -ne 0) { throw 'PC bridge compilation failed.' }
