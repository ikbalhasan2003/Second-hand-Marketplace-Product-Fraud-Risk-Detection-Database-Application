$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $workspaceRoot 'runtime\demo_processes.json'
if (-not (Test-Path -LiteralPath $processFile)) { Write-Host 'No managed demo process record exists.'; exit 0 }
$records = @(Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json)
foreach ($record in $records) {
    $running = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if ($running) {
        $expectedStart = [DateTime]::Parse($record.started).ToUniversalTime()
        $expectedPath = [IO.Path]::GetFullPath([string]$record.path)
        $workspacePython = [IO.Path]::GetFullPath((Join-Path $workspaceRoot '.venv\Scripts\python.exe'))
        if ($running.StartTime.ToUniversalTime() -ne $expectedStart -or $running.Path -ne $expectedPath -or $expectedPath -ne $workspacePython) {
            throw "Process $($record.id) no longer matches the recorded workspace process; it was left running."
        }
        # Windows venv launchers may own a real Python child. Stop that verified
        # launcher's process tree so the socket/worker is not orphaned.
        & taskkill.exe /PID $running.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Unable to stop verified process $($running.Id)." }
        Write-Host "Stopped $($record.role) process $($record.id)."
    }
}
Remove-Item -LiteralPath $processFile
