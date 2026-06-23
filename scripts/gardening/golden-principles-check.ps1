<#
.SYNOPSIS
    황금 원칙(Golden Principles, GP-1~10) 정적 점검 — 위반 '신호'를 보고한다.

.DESCRIPTION
    이 검사는 휴리스틱이다(증거가 아니라 신호). 진짜 강제는 테스트(test_cross_contamination,
    test_no_model_migration_drift 등)와 사람/에이전트 리뷰가 한다. 여기선 값싸게 잡히는 냄새만 본다.
    기본 report-only(exit 0). -Strict 면 신호 발견 시 exit 1. -OutFile 로 마크다운 리포트 저장(리뷰 코멘트용).
    원칙 정의: docs/design-docs/core-beliefs.md

.EXAMPLE
    ./scripts/gardening/golden-principles-check.ps1
    ./scripts/gardening/golden-principles-check.ps1 -OutFile review-notes.md
#>
param(
    [switch]$Strict,
    [string]$OutFile
)
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel)
Set-Location $root
$report = [System.Collections.Generic.List[string]]::new()
$signals = 0
function Note($line) { $script:report.Add($line); Write-Host $line }

Note "## 황금 원칙 점검 (휴리스틱 신호)"
Note ""

# --- GP-1: 서비스 쿼리의 테넌트 스코프 ---
Note "### GP-1 멀티테넌트 스코프"
$svc = Get-ChildItem -Path (Join-Path $root "app\services") -Filter *.py -Recurse -ErrorAction SilentlyContinue
$gp1 = 0
foreach ($f in $svc) {
    $t = Get-Content $f.FullName -Raw
    $buildsQuery = ($t -match '\.query\(' -or $t -match 'select\(' -or $t -match 'session\.execute')
    if ($buildsQuery -and ($t -notmatch 'company_id')) {
        Note "- ⚠ ``$($f.Name)`` : 쿼리를 만들지만 company_id 언급 없음 → 테넌트 스코프 확인 필요"
        $gp1++; $signals++
    }
}
if ($gp1 -eq 0) { Note "- ✓ 명백한 신호 없음" }
Note ""

# --- GP-8: dev DB 파괴 명령 ---
Note "### GP-8 dev DB 파괴 금지"
$scripts = Get-ChildItem -Path $root -Include *.ps1, *.bat, *.sh -Recurse -ErrorAction SilentlyContinue |
           Where-Object { $_.FullName -notmatch 'golden-principles-check' }
$gp8 = 0
foreach ($f in $scripts) {
    if ((Get-Content $f.FullName -Raw) -match 'alembic.*downgrade') {
        Note "- ⚠ ``$($f.Name)`` : 'alembic downgrade' 포함 → dev DB(./expense_ai.db) 직접 실행 아닌지 확인"
        $gp8++; $signals++
    }
}
if ($gp8 -eq 0) { Note "- ✓ 신호 없음" }
Note ""

# --- 정보성: TODO/FIXME 집계(기술부채 피드) ---
Note "### 정보성 — TODO/FIXME (tech-debt 후보)"
$todos = Get-ChildItem -Path (Join-Path $root "app") -Filter *.py -Recurse -ErrorAction SilentlyContinue |
         Select-String -Pattern 'TODO|FIXME' -ErrorAction SilentlyContinue
Note "- 발견: $($todos.Count) 건 (필요 시 tech-debt-ledger 로 승격)"
Note ""

Note "> 위는 신호일 뿐 위반 확정이 아니다. 진짜 강제는 테스트/리뷰가 한다."

if ($OutFile) {
    $report -join "`n" | Out-File -FilePath $OutFile -Encoding utf8
    Write-Host "`n[golden] 리포트 저장: $OutFile" -ForegroundColor Green
}
Write-Host "`n=== 신호 $signals 건 ===" -ForegroundColor Cyan
if ($Strict -and $signals -gt 0) { exit 1 }
exit 0
