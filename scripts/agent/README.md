# scripts/agent/ — 자율 PR 루프 (Ralph Wiggum)

사람 개입을 **머지 한 지점으로** 줄이는 자율 루프. 에이전트가 코드를 쓰고, 스스로 검증하고,
PR 을 열고, 리뷰를 주고받는다. 운영 규약: [docs/references/agent-operating-manual.md](../../docs/references/agent-operating-manual.md).

## 구성 요소
| 위치 | 역할 | 트리거 |
|------|------|--------|
| `ralph-loop.ps1` (여기) | **로컬** 루프: 에이전트→pytest→(apply 시)PR | 사람이 실행 |
| `.github/workflows/agent-pr-loop.yml` | **CI** 루프: 생성→테스트→(apply 시)PR | `workflow_dispatch` |
| `.github/workflows/agent-review.yml` | 에이전트 리뷰어(코멘트만) | PR 이벤트 |

## 안전 설계 (의도적 제약)
- **자동 머지 절대 없음** — 비가역 행동은 항상 사람 게이트.
- 로컬·CI 모두 **기본 dry-run**(생성·테스트만). `-Apply` / `mode=apply` 일 때만 브랜치+PR.
- 자동 트리거(push/schedule) 없음 — 루프는 명시적으로 시작한다.
- 리뷰어는 `pull-requests: write`(코멘트)만, 승인/머지 권한 없음.

## 결선 상태 (정직하게)
에이전트 **호출 단계는 placeholder** 다(tech-debt DEBT-5). 실제로 돌리려면:
1. 시크릿 `ANTHROPIC_API_KEY` 등록(CI) 또는 로컬에 `claude` CLI/Agent SDK 설치.
2. 로컬: `-AgentCommand 'claude -p "{task}"'` 처럼 호출 명령 주입.
3. CI: `agent-pr-loop.yml` 의 "Run agent" 스텝에서 동일하게 결선.

## 사용 예
```powershell
# 로컬, dry-run(안전): 검증 골격만
./scripts/agent/ralph-loop.ps1 -Task "docs/exec-plans/2026-06-16-tenant-whitelist.md"

# 로컬, 실제 PR 까지(에이전트 결선 후)
./scripts/agent/ralph-loop.ps1 -Task "용도 추천 캐시 추가" -AgentCommand 'claude -p "{task}"' -Apply
```
CI 에서는 Actions → "Agent PR Loop (Ralph)" → Run workflow 로 `task`/`mode` 입력.
