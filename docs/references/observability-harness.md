# 관측 하네스 (Observability Harness) — 에이전트의 '눈과 감각'

에이전트가 **사람의 확인 없이 스스로 "됐다"를 증명**하기 위한 환경. 두 축으로 구성된다:
(A) UI 검증(스냅샷/스크린샷), (B) 워크트리별 격리 로그/메트릭 스택. 구현은 [`scripts/observability/`](../../scripts/observability/).

## A. UI 검증 — Chrome DevTools Protocol (CDP)
프런트(`frontend/`, Vite, :5173)나 API 콘솔(`frontend/console.html`)을 띄운 뒤 DOM·스크린샷을 떠서 시각/구조를 검증한다.

```powershell
./scripts/observability/capture-ui.ps1 -Url http://localhost:5173 -OutDir .agent-artifacts/ui
```
- **무의존(권장 기본)**: 헤드리스 Chrome 의 `--screenshot`/`--dump-dom` 으로 PNG + DOM 스냅샷 저장. 추가 패키지 불필요.
- **풀 CDP(상호작용 필요 시)**: `--remote-debugging-port=9222` 로 띄워 WebSocket 으로 클릭/입력/콘솔/네트워크 로그까지 수집. 에이전트는 콘솔 에러·실패 네트워크 요청을 읽어 회귀를 자가 진단한다.
- **Claude Code MCP 경로**: 이 환경에는 `Claude_in_Chrome`/`Claude_Preview` MCP 도 있어, 스크립트 대신 그쪽으로 스냅샷·클릭·콘솔 수집이 가능하다(상호작용형 검증에 더 강력).

산출물은 워크트리 로컬 `.agent-artifacts/`(gitignore 권장)에 떨궈, 에이전트가 같은 세션 내에서 읽는다.

## B. 워크트리별 격리 로그/메트릭 스택
여러 에이전트가 git **worktree** 로 병렬 작업할 때, 스택이 충돌하지 않도록 워크트리마다 **고유 프로젝트명+포트 오프셋**으로 일시적 스택을 띄운다.

```powershell
./scripts/observability/obs-up.ps1     # 이 워크트리 전용 Loki+Promtail+Prometheus+Grafana 기동
./scripts/observability/obs-down.ps1   # 정리(-v 로 볼륨까지)
```
- 포트/프로젝트명은 **워크트리 경로 해시**로 결정 → 워크트리 간 충돌 없음.
- **LogQL**(Loki): 앱 로그를 쿼리해 에러율·특정 트레이스 추적.
  ```logql
  sum(rate({app="expense-ai"} |= "ERROR" [5m]))         # 5분 에러 발생률
  {app="expense-ai"} | json | tenant_id="C001"           # 특정 테넌트 로그(격리 검증)
  ```
- **PromQL**(Prometheus): 성능 자가 검증. 단, 앱에 `/metrics` 노출이 선행돼야 한다(현재 미도입 — [tech-debt-ledger.md](../exec-plans/tech-debt-ledger.md) DEBT-4).
  ```promql
  histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))  # p95 지연
  sum(rate(http_requests_total{status=~"5.."}[5m]))                                       # 5xx 비율
  ```

## 에이전트의 자가 검증 루프 (개념)
```
변경 → 앱 기동(run-local) → capture-ui(스냅샷) + LogQL(에러 0?) + PromQL(p95 회귀 없음?)
     → 기준 미달이면 원인 분석 → 재수정 → 반복
```
이 신호들이 exec-plan 의 "4. 검증 전략" 을 기계적으로 충족시키는 근거가 된다.
