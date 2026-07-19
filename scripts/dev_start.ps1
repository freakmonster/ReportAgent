# dev_start.ps1 - One-click local dev environment launcher
#
# Usage:
#   .\scripts\dev_start.ps1              # Full start
#   .\scripts\dev_start.ps1 -SkipCheck   # Skip service checks
#   .\scripts\dev_start.ps1 -MainOnly    # Main app only, no MCP sidecars

param(
    [switch]$SkipCheck,
    [switch]$MainOnly
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  Research Agent - Local Dev Environment" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Load API Keys
Write-Host "[1/4] Loading API keys..." -ForegroundColor Yellow

$env:TAVILY_API_KEY   = "YOUR_TAVILY_API_KEY"
$env:DEEPSEEK_API_KEY = "YOUR_DEEPSEEK_API_KEY"
$env:QWEN_API_KEY     = "YOUR_QWEN_API_KEY"

Write-Host "  TAVILY_API_KEY   = $($env:TAVILY_API_KEY.Substring(0,20))..."
Write-Host "  DEEPSEEK_API_KEY = $($env:DEEPSEEK_API_KEY.Substring(0,20))..."
Write-Host "  QWEN_API_KEY     = $($env:QWEN_API_KEY.Substring(0,20))..."
Write-Host ""

# 2. Check infrastructure
if (-not $SkipCheck) {
    Write-Host "[2/4] Checking PostgreSQL / Redis / Qdrant..." -ForegroundColor Yellow
    python "$ROOT\scripts\check_services.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  ABORT: Infrastructure not ready. Fix issues or use -SkipCheck." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

# 3. Start MCP sidecars
if (-not $MainOnly) {
    Write-Host "[3/4] Starting MCP sidecar services..." -ForegroundColor Yellow

    $servers = @(
        @{Name="mcp-search"; Port=8001; Module="mcp_tools.mcp_servers.search_server:app"},
        @{Name="mcp-chart";  Port=8003; Module="mcp_tools.mcp_servers.chart_server:app"},
        @{Name="mcp-email";  Port=8004; Module="mcp_tools.mcp_servers.email_server:app"}
    )

    foreach ($s in $servers) {
        Write-Host "  Starting $($s.Name) on port $($s.Port)..."
        Start-Process -FilePath "uvicorn" `
            -ArgumentList $s.Module, "--port", $s.Port, "--log-level", "warning" `
            -WindowStyle Minimized `
            -WorkingDirectory $ROOT
        Start-Sleep -Milliseconds 500
    }

    Write-Host "  3 MCP sidecars launched." -ForegroundColor Green
    Write-Host ""
}

# 4. Start main app
Write-Host "[4/4] Starting main application on http://localhost:8000" -ForegroundColor Yellow
Write-Host ""
Write-Host "  App:        http://localhost:8000" -ForegroundColor Green
Write-Host "  Health:     http://localhost:8000/health" -ForegroundColor Green
Write-Host "  API docs:   http://localhost:8000/docs" -ForegroundColor Green
if (-not $MainOnly) {
    Write-Host "  MCP Search: http://localhost:8001" -ForegroundColor Green
    Write-Host "  MCP Chart:  http://localhost:8003" -ForegroundColor Green
    Write-Host "  MCP Email:  http://localhost:8004" -ForegroundColor Green
}
Write-Host ""
Write-Host "  Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host "======================================================" -ForegroundColor Cyan

uvicorn app:app --host 127.0.0.1 --port 8000 --reload --log-level info
