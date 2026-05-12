Set-Location $PSScriptRoot
Write-Host ""
Write-Host " Regime Engine dashboard | http://127.0.0.1:8765/"
Write-Host " Press Ctrl+C to stop."
Write-Host ""
python -m http.server 8765
