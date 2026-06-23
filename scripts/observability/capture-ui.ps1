<#
.SYNOPSIS
    에이전트의 '눈' — 헤드리스 Chromium(CDP)으로 URL 의 스크린샷 + DOM 스냅샷을 떠서
    에이전트가 UI 를 시각/구조적으로 자가 검증할 수 있게 한다.

.DESCRIPTION
    무의존 기본 모드: 헤드리스 Chrome/Edge 의 --screenshot/--dump-dom 플래그만 쓴다(추가 패키지 불필요).
    산출물은 -OutDir(기본 .agent-artifacts/ui)에 저장되며, 같은 세션의 에이전트가 Read 로 확인한다.
    상호작용(클릭/입력/콘솔 수집)이 필요하면 -DebugPort 로 원격 디버깅을 열고 CDP 클라이언트(또는
    Claude_in_Chrome MCP)로 접속한다. 자세한 배경: docs/references/observability-harness.md

.EXAMPLE
    ./scripts/observability/capture-ui.ps1 -Url http://localhost:5173
    ./scripts/observability/capture-ui.ps1 -Url http://localhost:8000/docs -OutDir .agent-artifacts/api -DebugPort 9222
#>
param(
    [string]$Url = "http://localhost:5173",
    [string]$OutDir = ".agent-artifacts/ui",
    [int]$Width = 1440,
    [int]$Height = 900,
    [int]$DebugPort = 0    # >0 이면 원격 디버깅 모드(상호작용형). 0 이면 1회성 스냅샷.
)
$ErrorActionPreference = "Stop"

# 1) Chromium 계열 실행 파일 탐색: Chrome 우선, 없으면 Edge(Win11 기본 탑재).
$candidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
)
$browser = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    Write-Error "Chrome/Edge 실행 파일을 찾을 수 없습니다. 경로를 직접 지정하거나 설치하세요."
    exit 1
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$png = Join-Path $OutDir "shot-$stamp.png"
$dom = Join-Path $OutDir "dom-$stamp.html"

if ($DebugPort -gt 0) {
    # 상호작용 모드: 원격 디버깅 포트를 열고 백그라운드로 띄운다(CDP/MCP 가 접속).
    Write-Host "[capture-ui] 원격 디버깅 모드 — $browser :$DebugPort" -ForegroundColor Cyan
    $profileDir = Join-Path $env:TEMP "cdp-profile-$DebugPort"
    Start-Process $browser -ArgumentList @(
        "--headless=new", "--remote-debugging-port=$DebugPort",
        "--user-data-dir=$profileDir", "--window-size=$Width,$Height", $Url
    )
    Write-Host "CDP 엔드포인트: http://localhost:$DebugPort/json  (DevTools Protocol)" -ForegroundColor Green
    Write-Host "종료하려면 해당 프로세스를 Stop-Process 하세요." -ForegroundColor DarkGray
    exit 0
}

# 2) 1회성 스냅샷: 스크린샷과 DOM 덤프를 각각 수행(--dump-dom 은 stdout 으로 출력됨).
Write-Host "[capture-ui] screenshot → $png" -ForegroundColor Cyan
& $browser --headless=new --disable-gpu --hide-scrollbars `
    --window-size="$Width,$Height" --screenshot="$png" $Url | Out-Null

Write-Host "[capture-ui] dump-dom → $dom" -ForegroundColor Cyan
& $browser --headless=new --disable-gpu --dump-dom $Url > $dom

if ((Test-Path $png) -and (Test-Path $dom)) {
    Write-Host "[capture-ui] 완료. 에이전트는 다음을 Read 하세요:" -ForegroundColor Green
    Write-Host "  - 스크린샷: $png"
    Write-Host "  - DOM     : $dom"
} else {
    Write-Error "[capture-ui] 산출물 생성 실패 — 대상 URL 이 떠 있는지 확인하세요($Url)."
    exit 1
}
