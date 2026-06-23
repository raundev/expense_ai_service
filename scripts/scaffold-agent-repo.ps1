<#
.SYNOPSIS
    에이전트 우선(Agent-First) 리포 구조를 멱등하게 스캐폴딩한다.

.DESCRIPTION
    docs/ 지식 베이스 생태계와 scripts/ 하네스 디렉터리, .github/workflows 를 보장한다.
    **멱등**: 이미 있는 파일은 건드리지 않는다(풍부한 문서를 덮어쓰지 않음). 없는 디렉터리/인덱스 stub 만 만든다.
    재실행해도 변경이 0 이어야 정상이다(exec-plan 2026-06-16-agent-first-harness 의 검증 조건).

    이 스크립트는 구조의 '단일 진실 공급원'이다 — 새 디렉터리/seed 를 추가하려면 여기서 한다.
    배경: docs/README.md, docs/references/agent-operating-manual.md

.EXAMPLE
    ./scripts/scaffold-agent-repo.ps1
    ./scripts/scaffold-agent-repo.ps1 -WhatIf   # 무엇을 만들지 미리보기
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel)
Set-Location $root

# 보장할 디렉터리.
$dirs = @(
    "docs/design-docs", "docs/exec-plans", "docs/generated", "docs/product-specs", "docs/references",
    "scripts/observability", "scripts/agent", "scripts/gardening",
    ".github/workflows", ".agent-artifacts"
)

# 없으면 만들 최소 stub(경로 → 내용). 이미 있으면 절대 덮어쓰지 않는다.
$stubs = @{
    "docs/README.md"                  = "# docs/ — 지식 베이스`n`n자세한 지도는 scaffold 가 채운다. (placeholder)`n"
    "docs/design-docs/README.md"      = "# design-docs/ — 설계 & 핵심 신념`n"
    "docs/exec-plans/README.md"       = "# exec-plans/ — 실행 계획 & 기술 부채`n"
    "docs/generated/README.md"        = "# generated/ — 자동 생성물 (DO NOT EDIT)`n"
    "docs/product-specs/README.md"    = "# product-specs/ — 제품 명세`n"
    "docs/references/README.md"       = "# references/ — 참조 & 운영 매뉴얼`n"
}

$created = 0
foreach ($d in $dirs) {
    $full = Join-Path $root $d
    if (-not (Test-Path $full)) {
        if ($PSCmdlet.ShouldProcess($d, "mkdir")) {
            New-Item -ItemType Directory -Force -Path $full | Out-Null
            Write-Host "  + dir  $d" -ForegroundColor Green
            $created++
        }
    }
}
# .agent-artifacts 는 산출물 임시 폴더 — .gitkeep 으로 존재만 보장(내용은 gitignore 권장).
$gitkeep = Join-Path $root ".agent-artifacts/.gitkeep"
if (-not (Test-Path $gitkeep)) {
    if ($PSCmdlet.ShouldProcess(".agent-artifacts/.gitkeep", "touch")) {
        New-Item -ItemType File -Path $gitkeep | Out-Null; $created++
    }
}

foreach ($path in $stubs.Keys) {
    $full = Join-Path $root $path
    if (-not (Test-Path $full)) {
        if ($PSCmdlet.ShouldProcess($path, "write stub")) {
            New-Item -ItemType Directory -Force -Path (Split-Path $full) | Out-Null
            $stubs[$path] | Out-File -FilePath $full -Encoding utf8 -NoNewline
            Write-Host "  + stub $path" -ForegroundColor Green
            $created++
        }
    }
}

Write-Host "`n[scaffold] 완료. 신규 생성: $created 개." -ForegroundColor Cyan
if ($created -eq 0) { Write-Host "[scaffold] 이미 완비됨(멱등 OK)." -ForegroundColor Green }
Write-Host "다음: 루트 CLAUDE.md(목차) → docs/README.md → docs/references/agent-operating-manual.md 순으로 읽으세요." -ForegroundColor DarkGray
