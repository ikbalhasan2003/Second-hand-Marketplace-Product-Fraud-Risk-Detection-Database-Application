param(
    [switch]$SeedDemo,
    [switch]$ActivateModel
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspaceRoot
$pythonPath = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $localPython = Join-Path $workspaceRoot '.tools\python\cpython-3.13-windows-x86_64-none\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        & $localPython -m venv .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.13 -m venv .venv
    } else {
        throw 'Install Python 3.13 (including the py launcher) or create .venv with Python 3.13 first.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& $pythonPath -c "import sys; assert sys.version_info[:2] == (3,13), 'Python 3.13 is required'"
if ($LASTEXITCODE -ne 0) { throw 'Wrong Python interpreter.' }
& $pythonPath -m pip install -r requirements/lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    $secret = & $pythonPath -c "import secrets; print(secrets.token_urlsafe(48))"
    $content = Get-Content -LiteralPath '.env' -Raw
    $newContent = $content.Replace('replace-with-a-random-secret-at-least-50-characters-long', $secret)
    [IO.File]::WriteAllText((Join-Path $workspaceRoot '.env'), $newContent, (New-Object Text.UTF8Encoding($false)))
    Write-Host 'Created private .env. Configure PostgreSQL credentials there before rerunning setup.'
    exit 0
}
Write-Host 'Migrations require the owner connection. Never bootstrap database/install.sql before Django migrations.'
& $pythonPath manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Migration failed. Verify the empty database and owner credentials.' }
& $pythonPath manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Django configuration check failed.' }
& $pythonPath manage.py collectstatic --noinput
if ($LASTEXITCODE -ne 0) { throw 'Static collection failed.' }
if ($SeedDemo) {
    $demoArgs = @('manage.py', 'seed_demo')
    if ($ActivateModel) { $demoArgs += '--activate-model' }
    & $pythonPath @demoArgs
    if ($LASTEXITCODE -ne 0) { throw 'Demo provisioning failed; completed records are preserved for a safe retry.' }
}
Write-Host 'Setup complete. Use scripts/start_demo.ps1 after selecting web/worker runtime credentials.'
