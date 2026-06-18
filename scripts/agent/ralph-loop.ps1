<#
.SYNOPSIS
    로컬 자율 PR 루프(Ralph Wiggum) 래퍼 — 에이전트에게 작업을 시키고 자가 검증 후 (선택적으로) PR 까지.

.DESCRIPTION
    한 바퀴 = [에이전트 변경] → [pytest 자가 검증] → (-Apply 시) [브랜치+커밋+PR].
    안전 기본값: -Apply 없으면 dry-run(푸시/PR 안 함). **자동 머지는 절대 없음** — 머지는 사람이.
    에이전트 호출은 -AgentCommand 로 주입(플러그블). 미지정 시 호출 단계를 no-op 으로 스킵하고
    검증/PR 골격만 돈다(스켈레톤). 배경: docs/references/agent-operating-manual.md

.PARAMETER Task
    작업 지시 문자열 또는 exec-plan 파일 경로.

.PARAMETER AgentCommand
    에이전트를 호출하는 명령 템플릿. '{task}' 가 Task 로 치환된다.
    예: 'claude -p "{task}"'  또는  'python scripts/agent/run_agent.py "{task}"'

.EXAMPLE
    ./scripts/agent/ralph-loop.ps1 -Task "docs/exec-plans/2026-06-16-tenant-whitelist.md"
    ./scripts/agent/ralph-loop.ps1 -Task "용도 추천 캐시 추가" -AgentCommand 'claude -p "{task}"' -Apply
#>
param(
    [Parameter(Mandatory = $true)][string]$Task,
    [string]$AgentCommand,
    [int]$MaxIterations = 3,
    [string]$BaseBranch = "main",
    [switch]$Apply
)
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel)
Set-Location $root

# exec-plan 경로면 내용을 읽어 지시로 사용.
$taskText = $Task
if (Test-Path $Task) { $taskText = Get-Content $Task -Raw }

Write-Host "=== Ralph Loop ===" -ForegroundColor Cyan
Write-Host "Task   : $Task"
Write-Host "Apply  : $Apply  (dry-run=$(-not $Apply))"
Write-Host "Agent  : $(if ($AgentCommand) { $AgentCommand } else { '(미지정 — no-op 스켈레톤)' })"

for ($i = 1; $i -le $MaxIterations; $i++) {
    Write-Host "`n--- iteration $i / $MaxIterations ---" -ForegroundColor Yellow

    # 1) 에이전트가 변경을 만든다(플러그블). 미지정 시 스킵.
    if ($AgentCommand) {
        $cmd = $AgentCommand.Replace("{task}", $taskText.Replace('"', '`"'))
        Write-Host "[agent] $cmd"
        Invoke-Expression $cmd
    } else {
        Write-Host "[agent] AgentCommand 미지정 — 변경 생성 스킵(스켈레톤)." -ForegroundColor DarkGray
    }

    # 2) 자가 검증 게이트: 테스트.
    Write-Host "[verify] python -m pytest -q"
    python -m pytest -q
    $testsPassed = ($LASTEXITCODE -eq 0)
    Write-Host "[verify] tests passed = $testsPassed"

    if ($testsPassed) { break }
    if (-not $AgentCommand) { break }  # 스켈레톤은 무한 반복 방지
    Write-Host "[loop] 실패 — 다음 이터레이션에서 에이전트가 수정 시도." -ForegroundColor DarkYellow
}

# 3) (Apply 시) 변경이 있으면 브랜치+커밋+PR. 머지는 안 함.
if (-not $Apply) {
    Write-Host "`n[dry-run] 여기까지. 푸시/PR 생략. 실제 PR 은 -Apply 로." -ForegroundColor Green
    exit 0
}
if (-not (git status --porcelain)) {
    Write-Host "`n[apply] 변경 없음 — PR 생략." -ForegroundColor Green
    exit 0
}

$branch = "agent/ralph-" + (Get-Date -Format "yyyyMMdd-HHmmss")
Write-Host "`n[apply] 브랜치 $branch 생성 → 커밋 → 푸시 → PR" -ForegroundColor Cyan
git checkout -b $branch
git add -A
git commit -m "agent(ralph): $Task"
git push origin $branch
gh pr create --base $BaseBranch --head $branch --title "agent(ralph): $Task" `
    --body "로컬 Ralph 루프가 생성. **자동 머지 없음** — 사람 리뷰/머지 필요."
Write-Host "[apply] PR 생성 완료. 머지는 사람이." -ForegroundColor Green
