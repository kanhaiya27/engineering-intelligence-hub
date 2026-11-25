<#
Start everything EIH needs on laptop-a, in order, and check each step.

    powershell -ExecutionPolicy Bypass -File scripts\start_eih.ps1          # services + API + web UI
    powershell -ExecutionPolicy Bypass -File scripts\start_eih.ps1 -NoWeb   # services + API only

1. Docker (Qdrant :6333, Neo4j :7474/:7687; bound to 127.0.0.1).
2. Ollama 0.35.1 server, started directly. The tray app is not used: it auto-updates, and a
   changed Ollama version makes results incomparable (CLAUDE.md, pinned digests).
3. FastAPI on http://127.0.0.1:8000 (docs at /docs).
4. Web UI on http://127.0.0.1:5173.
Nothing here writes research data.
#>
param([switch]$NoWeb)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Wait-Url($url, $name, $seconds = 90) {
    for ($i = 0; $i -lt $seconds; $i += 2) {
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 $url | Out-Null; Write-Host "  $name is up"; return } catch { Start-Sleep -Seconds 2 }
    }
    throw "$name did not come up at $url"
}

Write-Host '[1/4] Docker services'
& "C:\Program Files\Docker\Docker\resources\bin\docker.exe" compose up -d
Wait-Url 'http://127.0.0.1:6333/readyz' 'Qdrant'
Wait-Url 'http://127.0.0.1:7474' 'Neo4j'

Write-Host '[2/4] Ollama server'
$ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:11434/api/version' | Out-Null; Write-Host '  already running' }
catch {
    Get-Process -Name 'ollama app' -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden `
        -RedirectStandardError "$env:LOCALAPPDATA\Ollama\serve-direct.log" -RedirectStandardOutput "$env:LOCALAPPDATA\Ollama\serve-direct.out.log"
    Wait-Url 'http://127.0.0.1:11434/api/version' 'Ollama'
}
$v = (Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:11434/api/version').Content
if ($v -notmatch '"0\.35\.1"') { Write-Warning "Ollama reports $v, not 0.35.1: results would not be comparable with the pinned runs." }

Write-Host '[3/4] API'
Start-Process -FilePath "$root\.venv311\Scripts\python.exe" -ArgumentList '-m','uvicorn','apps.api.main:app','--host','127.0.0.1','--port','8000' -WindowStyle Minimized
Wait-Url 'http://127.0.0.1:8000/health' 'API'

if (-not $NoWeb) {
    Write-Host '[4/4] Web UI'
    $env:Path = "$env:LOCALAPPDATA\Programs\nodejs;$env:Path"
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm','run','dev' -WorkingDirectory "$root\web" -WindowStyle Minimized
    Wait-Url 'http://127.0.0.1:5173' 'Web UI'
    Start-Process 'http://127.0.0.1:5173'
}
Write-Host 'Ready. Status page: http://127.0.0.1:5173/status   API docs: http://127.0.0.1:8000/docs'
