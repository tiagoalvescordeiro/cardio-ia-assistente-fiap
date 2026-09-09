#Requires -Version 5.1
<#
.SYNOPSIS
  Expõe o CardioIA (porta 5000) via Cloudflare Quick Tunnel (gratuito, reversível).

.DESCRIPTION
  Pré-requisito: Flask rodando (python backend/app.py) com FLASK_HOST=0.0.0.0.
  Instale cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
  Ou: winget install Cloudflare.cloudflared

  A URL pública https://*.trycloudflare.com aparece no stdout.
  Ctrl+C encerra o túnel. Não cole dados reais de pacientes.
#>
param(
    [int]$Port = 5000,
    [string]$LocalHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$target = "http://${LocalHost}:${Port}"

function Find-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path (Split-Path $PSScriptRoot -Parent) "tools\cloudflared.exe"),
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\cloudflared\cloudflared.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$bin = Find-Cloudflared
if (-not $bin) {
    Write-Host "cloudflared não encontrado no PATH."
    Write-Host "Instale com: winget install Cloudflare.cloudflared"
    Write-Host "Ou baixe o binário em: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    Write-Host ""
    Write-Host "Alternativa ngrok (também gratuita para quickstart):"
    Write-Host "  ngrok http $Port"
    exit 1
}

try {
    $health = Invoke-RestMethod -Uri "$target/api/health" -TimeoutSec 3
    Write-Host "Backend OK: status=$($health.status) watson=$($health.watson_mode) llm=$($health.llm_mode)"
} catch {
    Write-Host "AVISO: não foi possível alcançar $target/api/health."
    Write-Host "Suba o Flask antes: python backend/app.py"
    Write-Host "Continuando mesmo assim..."
}

Write-Host "Iniciando túnel → $target"
Write-Host "A URL pública (trycloudflare.com) será impressa abaixo. Ctrl+C para encerrar."
Write-Host ""

& $bin tunnel --url $target
