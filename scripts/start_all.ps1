param(
    [int]$FrontendPort = 3000,
    [int]$RagApiPort = 8601,
    [int]$ReviewApiPort = 8602,
    [switch]$InstallFrontend
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Frontend = Join-Path $Root "frontend"
$LocalPython = Join-Path $Root "venv\Scripts\python.exe"
$SystemPython = "C:\Users\hom02\AppData\Local\Programs\Python\Python314\python.exe"

if (Test-Path $env:PYTHON_BIN) {
    $Python = $env:PYTHON_BIN
} elseif (Test-Path $SystemPython) {
    $Python = $SystemPython
} elseif (Test-Path $LocalPython) {
    $Python = $LocalPython
} else {
    $Python = "python"
}

if (-not $env:HOME) {
    $env:HOME = $env:USERPROFILE
}

if ($InstallFrontend -or -not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location $Frontend
    npm.cmd install
    Pop-Location
}

Write-Host "Starting RAG API on http://localhost:$RagApiPort" -ForegroundColor Green
Start-Process -FilePath $Python -ArgumentList @(
    "-m", "rag_app.api_server",
    "--port", "$RagApiPort"
) -WorkingDirectory $Root -WindowStyle Hidden

Write-Host "Starting Review API on http://localhost:$ReviewApiPort" -ForegroundColor Green
Start-Process -FilePath $Python -ArgumentList @(
    "-m", "review_app.api_server",
    "--port", "$ReviewApiPort"
) -WorkingDirectory $Root -WindowStyle Hidden

Write-Host "Starting React frontend on http://localhost:$FrontendPort" -ForegroundColor Green
Start-Process -FilePath "npm.cmd" -ArgumentList @(
    "run", "dev", "--", "--port", "$FrontendPort"
) -WorkingDirectory $Frontend -WindowStyle Hidden

Write-Host ""
Write-Host "All apps are starting:" -ForegroundColor Cyan
Write-Host "  RAG API:       http://localhost:$RagApiPort"
Write-Host "  Review API:    http://localhost:$ReviewApiPort"
Write-Host "  React UI:      http://localhost:$FrontendPort"
Write-Host ""
Write-Host "To stop them, close the related python/node processes from Task Manager or run:"
Write-Host "  Get-Process python,node | Stop-Process"
