<#
.SYNOPSIS
    obs-up.ps1 로 띄운 이 워크트리의 관측 스택을 정리한다(같은 프로젝트명 파생 로직 사용).
.EXAMPLE
    ./scripts/observability/obs-down.ps1            # 컨테이너 정리
    ./scripts/observability/obs-down.ps1 -Volumes   # 볼륨까지 삭제
#>
param([switch]$Volumes)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

try { $root = (git rev-parse --show-toplevel) 2>$null } catch { $root = $null }
if (-not $root) { $root = Split-Path -Parent (Split-Path -Parent $here) }

$bytes = [System.Text.Encoding]::UTF8.GetBytes($root.ToLower())
$hash = ([System.Security.Cryptography.MD5]::Create()).ComputeHash($bytes)
$offset = ([int]$hash[0] + [int]$hash[1] * 256) % 200
$env:COMPOSE_PROJECT_NAME = "obs_" + ([System.IO.Path]::GetFileName($root)).ToLower() + "_$offset"
# down 시에도 compose 가 포트 변수를 참조하므로 동일하게 채워준다(미설정 경고 방지).
$env:OBS_LOKI_PORT = 3100 + $offset; $env:OBS_PROM_PORT = 9090 + $offset
$env:OBS_GRAFANA_PORT = 3000 + $offset; $env:OBS_LOG_DIR = Join-Path $root "logs"

$composeArgs = @("-f", (Join-Path $here "obs-stack.compose.yml"), "down")
if ($Volumes) { $composeArgs += "-v" }
Write-Host "[obs-down] project=$($env:COMPOSE_PROJECT_NAME) (volumes=$Volumes)" -ForegroundColor Cyan
docker compose @composeArgs
