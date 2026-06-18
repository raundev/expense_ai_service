<#
.SYNOPSIS
    Doc-gardening 점검 — 문서↔코드/문서↔문서 드리프트를 보고한다.

.DESCRIPTION
    세 가지를 검사한다:
      1) 깨진 상대 링크: CLAUDE.md + docs/**/*.md 의 마크다운 링크가 실제 파일을 가리키는가.
      2) stale exec-plan: status=active 인데 updated 가 -StaleDays(기본 30) 보다 오래됨.
      3) DB 스키마 드리프트: gen-db-schema.py --check (시스템 python 필요, 없으면 skip).
    기본은 report-only(exit 0). -CI 면 드리프트 발견 시 exit 1.

.EXAMPLE
    ./scripts/gardening/doc-drift-check.ps1
    ./scripts/gardening/doc-drift-check.ps1 -CI
#>
param(
    [int]$StaleDays = 30,
    [switch]$CI,
    [switch]$SkipSchema
)
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel)
Set-Location $root
$problems = 0

Write-Host "=== doc-drift-check ===" -ForegroundColor Cyan

# --- 1) 깨진 링크 ---
Write-Host "`n[1] 마크다운 링크 점검..." -ForegroundColor Yellow
$mdFiles = @(Get-Item (Join-Path $root "CLAUDE.md") -ErrorAction SilentlyContinue) +
           @(Get-ChildItem -Path (Join-Path $root "docs") -Recurse -Filter *.md -ErrorAction SilentlyContinue)
$linkRe = [regex]'\]\(([^)]+)\)'
foreach ($f in $mdFiles) {
    if (-not $f) { continue }
    $text = Get-Content $f.FullName -Raw
    foreach ($m in $linkRe.Matches($text)) {
        $target = $m.Groups[1].Value.Trim()
        # 외부/앵커/메일은 건너뛴다.
        if ($target -match '^(https?:|mailto:|#)') { continue }
        $path = ($target -split '#')[0]            # 앵커 제거
        if ([string]::IsNullOrWhiteSpace($path)) { continue }
        $resolved = Join-Path $f.DirectoryName $path
        if (-not (Test-Path $resolved)) {
            Write-Host "  ✗ $($f.Name): 깨진 링크 → $target" -ForegroundColor Red
            $problems++
        }
    }
}
if ($problems -eq 0) { Write-Host "  ✓ 깨진 링크 없음" -ForegroundColor Green }

# --- 2) stale exec-plan ---
Write-Host "`n[2] stale exec-plan 점검 (>${StaleDays}일)..." -ForegroundColor Yellow
$plans = Get-ChildItem -Path (Join-Path $root "docs\exec-plans") -Filter *.md -ErrorAction SilentlyContinue |
         Where-Object { $_.Name -notmatch '^(_|README)' }
foreach ($p in $plans) {
    $raw = Get-Content $p.FullName -Raw
    if ($raw -match '(?m)^status:\s*active' -and $raw -match '(?m)^updated:\s*(\d{4}-\d{2}-\d{2})') {
        $updated = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd', $null)
        $age = (Get-Date) - $updated
        if ($age.Days -gt $StaleDays) {
            Write-Host "  ⚠ $($p.Name): active 인데 $($age.Days)일째 미갱신" -ForegroundColor DarkYellow
            $problems++
        }
    }
}
Write-Host "  (점검 완료)" -ForegroundColor Green

# --- 3) DB 스키마 드리프트 ---
if (-not $SkipSchema) {
    Write-Host "`n[3] DB 스키마 드리프트 점검..." -ForegroundColor Yellow
    try {
        python (Join-Path $root "scripts\gardening\gen-db-schema.py") --check
        if ($LASTEXITCODE -ne 0) { $problems++ }
    } catch {
        Write-Host "  (시스템 python/앱 스택 없음 — skip)" -ForegroundColor DarkGray
    }
}

# --- 결과 ---
Write-Host "`n=== 결과: 드리프트 $problems 건 ===" -ForegroundColor Cyan
if ($CI -and $problems -gt 0) { exit 1 }
exit 0
