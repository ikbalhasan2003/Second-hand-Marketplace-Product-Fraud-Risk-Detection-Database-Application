param([int]$Port = 8000, [switch]$WithWorker)
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspaceRoot
$pythonPath = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup_windows.ps1 first.' }
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose a local port from 1024 through 65535.' }
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw "Port $Port is already in use. Reuse the running application or choose another port." }
New-Item -ItemType Directory -Force -Path runtime | Out-Null
$processFile = Join-Path $workspaceRoot 'runtime\demo_processes.json'
if (Test-Path -LiteralPath $processFile) { throw 'A demo process record exists. Run scripts/stop_demo.ps1 or inspect runtime/demo_processes.json.' }
& $pythonPath manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Django checks failed; inspect .env and database configuration.' }
$processes = @()
$web = Start-Process -FilePath $pythonPath -ArgumentList @('manage.py', 'runserver', "127.0.0.1:$Port", '--noreload') -WorkingDirectory $workspaceRoot -WindowStyle Hidden -RedirectStandardOutput 'runtime\web.out.log' -RedirectStandardError 'runtime\web.err.log' -PassThru
$processes += @{ role = 'web'; id = $web.Id; started = $web.StartTime.ToUniversalTime().ToString('o'); path = $web.Path }
if ($WithWorker) {
    $worker = Start-Process -FilePath $pythonPath -ArgumentList @('manage.py', 'run_risk_worker') -WorkingDirectory $workspaceRoot -WindowStyle Hidden -RedirectStandardOutput 'runtime\worker.out.log' -RedirectStandardError 'runtime\worker.err.log' -PassThru
    $processes += @{ role = 'worker'; id = $worker.Id; started = $worker.StartTime.ToUniversalTime().ToString('o'); path = $worker.Path }
}
$processes | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding utf8
Start-Sleep -Seconds 2
if ($web.HasExited) { throw 'Web process stopped. Inspect runtime/web.err.log and runtime/web.out.log.' }
Write-Host "Buyer: http://127.0.0.1:$Port/buyer-app/"
Write-Host "Seller: http://127.0.0.1:$Port/seller-app/"
Write-Host "Admin: http://127.0.0.1:$Port/admin-app/"
Write-Host 'Private demo credentials: runtime/DEMO_CREDENTIALS.txt. Logs: runtime/*.log.'
