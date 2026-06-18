<#
.SYNOPSIS
    로컬 개발 실행 헬퍼 — Dockerfile CMD 와 동일하게 "마이그레이션(head) 적용 후 서버 기동".

.DESCRIPTION
    이 프로젝트는 인터프리터가 분리돼 있다:
      - alembic 은 .venv 에만 설치돼 있다(시스템 python 에는 없음).
      - 앱(langchain/langgraph 등 풀스택)은 시스템 python 에 설치돼 있다.
    둘 다 .env 의 DB_URL(기본 ./expense_ai.db)을 가리키므로 같은 DB 에 적용된다.

    운영(Docker)은 이미 `alembic upgrade head && uvicorn ...` 로 기동하지만(Dockerfile),
    로컬에서 uvicorn 을 직접 띄우면 그 업그레이드가 빠져 '미적용' 500 이 났다. 이 스크립트가 그 격차를 메운다.

.EXAMPLE
    ./scripts/run-local.ps1
    ./scripts/run-local.ps1 -Port 8001 -NoReload
#>
param(
    [int]$Port = 8000,
    [switch]$NoReload
)
$ErrorActionPreference = "Stop"

# 프로젝트 루트(= scripts/ 의 상위)에서 실행해야 alembic.ini 와 ./expense_ai.db 가 해석된다.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$alembic = Join-Path $root ".venv\Scripts\alembic.exe"
if (-not (Test-Path $alembic)) {
    Write-Error ".venv 의 alembic 을 찾을 수 없습니다: $alembic`n먼저 .venv 에 requirements.txt 를 설치하세요."
    exit 1
}

# 네이티브 명령(alembic/python)은 정보성 로그를 stderr 로 내보낸다. PowerShell 5.1 은
# 출력이 캡처/리다이렉트되는 컨텍스트(비대화형 실행·VS Code 통합 터미널·CI·파이프)에서 그
# stderr 를 NativeCommandError 레코드로 감싸므로, $ErrorActionPreference='Stop' 이면 alembic 의
# 첫 "INFO ... Context impl SQLiteImpl." 한 줄에 스크립트가 종료된다(마이그레이션은 실제로
# 성공(exit 0)했는데도!). uvicorn 역시 INFO 를 stderr 로 내보내 같은 이유로 즉시 죽는다.
# 따라서 여기서부터는 Continue 로 낮추고, 네이티브 명령의 성공 여부는 종료코드($LASTEXITCODE)로 판정한다.
$ErrorActionPreference = "Continue"

Write-Host "[run-local] alembic upgrade head ..." -ForegroundColor Cyan
& $alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Error "alembic upgrade 실패 (exit=$LASTEXITCODE)"
    exit 1
}

Write-Host "[run-local] uvicorn 기동 (port=$Port, reload=$(-not $NoReload)) ..." -ForegroundColor Cyan
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if (-not $NoReload) { $uvicornArgs += "--reload" }

# 앱은 풀스택(qdrant_client·langchain 등)을 보유한 '시스템 python' 으로 구동해야 한다.
# .venv 가 활성화된 셸(프롬프트의 "(.venv)")에서 그냥 `python` 을 호출하면 .venv 인터프리터
# (= alembic 전용, 앱 의존성 없음)가 잡혀 `ModuleNotFoundError: qdrant_client` 로 깨진다.
# 그래서 활성 venv 를 '이 프로세스 한정' 으로 PATH 에서 떼어내고 VIRTUAL_ENV 를 해제해,
# `python` 이 PATH 상의 시스템 python 으로 해석되게 한다(사용자 셸의 활성 상태는 그대로 유지).
# (참고: Windows `py` 런처는 기본 등록 버전을 골라 풀스택이 아닌 다른 버전을 띄울 수 있어 부적합.)
if ($env:VIRTUAL_ENV) {
    $venvRoot = $env:VIRTUAL_ENV
    Write-Host "[run-local] 활성 venv 우회: $venvRoot → 앱은 시스템 python 으로 구동" -ForegroundColor DarkYellow
    $env:PATH = ($env:PATH -split ';' | Where-Object { $_ -and -not $_.StartsWith($venvRoot, [System.StringComparison]::OrdinalIgnoreCase) }) -join ';'
    Remove-Item Env:\VIRTUAL_ENV -ErrorAction SilentlyContinue
}
python @uvicornArgs
