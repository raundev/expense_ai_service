<#
.SYNOPSIS
    이 워크트리 전용의 일시적 관측 스택(Loki+Promtail+Prometheus+Grafana)을 기동한다.

.DESCRIPTION
    워크트리 경로를 해시해 결정론적 포트 오프셋(0~199)과 COMPOSE_PROJECT_NAME 을 만든다.
    덕분에 여러 git worktree 가 동시에 스택을 띄워도 포트/컨테이너/볼륨이 충돌하지 않는다.
    배경/쿼리 예시: docs/references/observability-harness.md

.EXAMPLE
    ./scripts/observability/obs-up.ps1
#>
param(
    [string]$LogDir   # 앱 로그 디렉터리(기본: <root>/logs)
)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

# 워크트리 루트(없으면 스크립트 상위의 상위).
try { $root = (git rev-parse --show-toplevel) 2>$null } catch { $root = $null }
if (-not $root) { $root = Split-Path -Parent (Split-Path -Parent $here) }

# 경로 해시 → 0~199 오프셋(포트군이 서로 겹치지 않게 ×1 로 분배).
$bytes = [System.Text.Encoding]::UTF8.GetBytes($root.ToLower())
$md5 = [System.Security.Cryptography.MD5]::Create()
$hash = $md5.ComputeHash($bytes)
$offset = ([int]$hash[0] + [int]$hash[1] * 256) % 200

$env:COMPOSE_PROJECT_NAME = "obs_" + ([System.IO.Path]::GetFileName($root)).ToLower() + "_$offset"
$env:OBS_LOKI_PORT    = 3100 + $offset
$env:OBS_PROM_PORT    = 9090 + $offset
$env:OBS_GRAFANA_PORT = 3000 + $offset
if ($LogDir) { $env:OBS_LOG_DIR = $LogDir } else { $env:OBS_LOG_DIR = Join-Path $root "logs" }
New-Item -ItemType Directory -Force -Path $env:OBS_LOG_DIR | Out-Null

Write-Host "[obs-up] project=$($env:COMPOSE_PROJECT_NAME)  offset=$offset" -ForegroundColor Cyan
docker compose -f (Join-Path $here "obs-stack.compose.yml") up -d
if ($LASTEXITCODE -ne 0) { Write-Error "docker compose up 실패 (Docker 데몬 확인)"; exit 1 }

Write-Host "`n[obs-up] 준비 완료 — 에이전트는 아래 HTTP API 로 자가 검증:" -ForegroundColor Green
Write-Host "  Grafana   : http://localhost:$($env:OBS_GRAFANA_PORT)  (anon admin)"
Write-Host "  Loki(API) : http://localhost:$($env:OBS_LOKI_PORT)/loki/api/v1/query_range"
Write-Host "  Prom(API) : http://localhost:$($env:OBS_PROM_PORT)/api/v1/query"
Write-Host "`n예시 LogQL : sum(rate({app=`"expense-ai`"} |= `"ERROR`" [5m]))" -ForegroundColor DarkGray
Write-Host "예시 PromQL: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))" -ForegroundColor DarkGray
