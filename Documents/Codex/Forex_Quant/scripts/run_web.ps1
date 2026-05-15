$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
  $python = $pythonCommand.Source
} elseif (Test-Path "C:\Python312\python.exe") {
  $python = "C:\Python312\python.exe"
} else {
  throw "Python was not found on PATH and C:\Python312\python.exe does not exist."
}

& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
