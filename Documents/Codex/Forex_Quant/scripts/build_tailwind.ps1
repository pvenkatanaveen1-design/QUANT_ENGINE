$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$tailwindExe = Join-Path $projectRoot ".tools\\tailwindcss-windows-x64.exe"
$tailwindUrl = "https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-windows-x64.exe"
$inputCss = Join-Path $projectRoot "app\\static\\css\\tailwind.input.css"
$outputCss = Join-Path $projectRoot "app\\static\\css\\tailwind.generated.css"
$configPath = Join-Path $projectRoot "tailwind.config.cjs"

if (-not (Test-Path $tailwindExe)) {
  New-Item -ItemType Directory -Path (Split-Path -Parent $tailwindExe) -Force | Out-Null
  Invoke-WebRequest -Uri $tailwindUrl -OutFile $tailwindExe
}

& $tailwindExe -c $configPath -i $inputCss -o $outputCss --minify

