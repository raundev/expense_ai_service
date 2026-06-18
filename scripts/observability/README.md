# scripts/observability/ — 관측 하네스 (에이전트의 눈)

에이전트가 사람 없이 변경을 자가 검증하기 위한 도구 모음. 개념·쿼리 예시는
[docs/references/observability-harness.md](../../docs/references/observability-harness.md) 참고.

## 구성
| 파일 | 역할 |
|------|------|
| `capture-ui.ps1` | 헤드리스 Chromium(CDP)으로 스크린샷 + DOM 스냅샷. 상호작용은 `-DebugPort`. |
| `obs-up.ps1` / `obs-down.ps1` | **워크트리별 격리** 로그/메트릭 스택 기동/정리(포트는 경로 해시로 파생). |
| `obs-stack.compose.yml` | Loki + Promtail + Prometheus + Grafana. |
| `prometheus.yml` / `promtail-config.yml` | 스크레이프/수집 설정. |

## 빠른 사용
```powershell
# 1) UI 스냅샷 (앱/프런트가 떠 있어야 함)
./scripts/observability/capture-ui.ps1 -Url http://localhost:5173

# 2) 로그/메트릭 스택 (Docker 필요)
./scripts/observability/obs-up.ps1
#   → Loki/Prometheus HTTP API 로 LogQL/PromQL 자가 검증
./scripts/observability/obs-down.ps1 -Volumes
```

## 전제/한계 (정직하게)
- **Docker 필요**: obs 스택은 docker compose 로 뜬다.
- **메트릭**: 앱에 `/metrics` 가 있어야 PromQL 이 의미를 가진다 — 현재 미도입(tech-debt DEBT-4). 로그(LogQL)는 앱이 `./logs/*.log` 로 파일 로깅하면 즉시 동작.
- **MCP 대안**: 상호작용형 UI 검증은 `Claude_in_Chrome`/`Claude_Preview` MCP 가 더 강력하다(스크립트는 무의존 폴백).
- 산출물(`.agent-artifacts/`)은 `.gitignore` 에 두는 것을 권장.
