@echo off
REM cmd(명령 프롬프트)에서도 바로 실행할 수 있도록 PowerShell 스크립트를 감싸는 래퍼.
REM   사용: scripts\run-local.bat                (기본 포트 8000)
REM         scripts\run-local.bat -Port 8001     (포트 변경)
REM         scripts\run-local.bat -NoReload      (자동 리로드 끄기)
REM %~dp0 = 이 .bat 의 폴더(scripts\) → 어느 위치에서 호출하든 옆의 .ps1 을 찾는다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-local.ps1" %*
