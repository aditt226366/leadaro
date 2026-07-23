<#
  run.ps1 — one script to stop/start the three backend services.

  Usage (from anywhere):
      .\run.ps1            # restart: kill-all then start-all  (default)
      .\run.ps1 stop       # kill-all only
      .\run.ps1 start      # start-all only
      .\run.ps1 status     # list running services + their interpreter

  Every service is launched with the venv interpreter by ABSOLUTE PATH
  (.venv\Scripts\python.exe) — never a bare `python`, which on this machine
  resolves through PATH to the system Python at ...\Programs\Python\Python312.

  NOTE: the "duplicate process" bug was the venv's python.exe being a launcher
  STUB that re-spawned the base interpreter. That was repaired by replacing the
  stub with a real interpreter copy; the old stub is kept at
  .venv\Scripts\python.exe.venvlauncher.bak. Each service is now ONE process.
#>
param(
  [ValidateSet('restart','stop','start','status')]
  [string]$Action = 'restart'
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv\Scripts\python.exe'
$LogDir = Join-Path $Root 'logs'

# One regex that matches all three services' command lines, so a leftover is
# caught no matter which interpreter launched it (venv, system, or old stub).
$Match = 'worker\.py|post_call\.py|uvicorn|services[\\/]api'

function Get-Services {
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match 'python' -and $_.CommandLine -match $Match }
}

function Stop-All {
  $procs = Get-Services
  if (-not $procs) { Write-Host 'stop: nothing running' -ForegroundColor DarkGray; return }
  foreach ($p in $procs) {
    Write-Host ("stop: killing PID {0}  ({1})" -f $p.ProcessId, $p.Name) -ForegroundColor Yellow
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Milliseconds 800
  # Any base-interpreter children of a launcher stub are orphaned by the kill
  # above; sweep once more so a stale stub-child can't linger.
  $left = Get-Services
  if ($left) { $left | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }
  Write-Host 'stop: all stopped' -ForegroundColor Green
}

function Assert-Venv {
  if (-not (Test-Path $Venv)) { throw "venv python not found at $Venv" }
  $prefix = & $Venv -c 'import sys; print(sys.prefix)'
  if ($prefix.Trim() -ne $Root + '\.venv' -and $prefix.Trim() -ne (Join-Path $Root '.venv')) {
    Write-Host "warn: venv sys.prefix is '$prefix' (expected $Root\.venv)" -ForegroundColor Yellow
  }
}

function Start-One($name, $argList) {
  $out = Join-Path $LogDir "$name.out.log"
  $err = Join-Path $LogDir "$name.err.log"
  $p = Start-Process -FilePath $Venv -ArgumentList $argList `
        -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
  Write-Host ("start: {0,-10} PID {1}" -f $name, $p.Id) -ForegroundColor Green
}

function Start-All {
  Assert-Venv
  if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
  # Refuse to stack a second copy on top of a running set.
  if (Get-Services) {
    Write-Host 'start: services already running — run "stop" first (or "restart")' -ForegroundColor Yellow
    return
  }
  Start-One 'worker'    @('services\agent\worker.py','start')
  Start-One 'post_call' @('services\agent\post_call.py')
  Start-One 'api'       @('-m','uvicorn','main:app','--app-dir','services\api','--host','127.0.0.1','--port','8000')
  Write-Host 'start: all up (logs in .\logs\*.out.log / *.err.log)' -ForegroundColor Green
}

function Show-Status {
  $procs = Get-Services
  if (-not $procs) { Write-Host 'status: no services running' -ForegroundColor DarkGray; return }
  foreach ($p in $procs) {
    $venvRun = $p.ExecutablePath -like (Join-Path $Root '.venv*')
    $tag = if ($venvRun) { 'VENV  ' } else { 'NON-VENV!' }
    $color = if ($venvRun) { 'Green' } else { 'Red' }
    $svc = if ($p.CommandLine -match 'worker\.py') { 'worker' }
           elseif ($p.CommandLine -match 'post_call\.py') { 'post_call' }
           else { 'api' }
    Write-Host ("{0}  {1,-10} PID {2,-6} {3}" -f $tag, $svc, $p.ProcessId, $p.ExecutablePath) -ForegroundColor $color
  }
}

switch ($Action) {
  'stop'    { Stop-All }
  'start'   { Start-All }
  'status'  { Show-Status }
  'restart' { Stop-All; Start-All }
}
