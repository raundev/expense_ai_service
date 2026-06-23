# scripts/gardening/ — 자동 정원 관리 (엔트로피 / 가비지 컬렉션)

에이전트가 코드를 계속 생성하면 문서·일관성이 부패한다. 이 도구들은 그 부패를 *적발*하고
(apply 시) *동기화*해 리포를 건강하게 유지한다. 원칙 정의: [core-beliefs.md](../../docs/design-docs/core-beliefs.md).

## 구성
| 파일 | 역할 | 강제 방식 |
|------|------|-----------|
| `gen-db-schema.py` | 모델 → `docs/generated/db-schema.md` 재생성 | `--check` 로 드리프트 검사 |
| `doc-drift-check.ps1` | 깨진 링크 · stale exec-plan · 스키마 드리프트 점검 | `-CI` 면 드리프트 시 실패 |
| `golden-principles-check.ps1` | GP-1~10 위반 '신호' 정적 점검 | `-Strict` / `-OutFile`(리뷰 코멘트) |

연동 워크플로: `.github/workflows/doc-gardening.yml`(주기 점검+동기화 PR), `agent-review.yml`(PR 코멘트).

## 사용
```powershell
python scripts/gardening/gen-db-schema.py            # 스키마 문서 재생성
python scripts/gardening/gen-db-schema.py --check    # 드리프트만 검사
./scripts/gardening/doc-drift-check.ps1              # 전체 드리프트 점검(report-only)
./scripts/gardening/golden-principles-check.ps1      # 황금 원칙 신호
```

## 철학 (정직한 한계)
- **휴리스틱은 신호지 판결이 아니다.** 진짜 강제는 테스트(`test_cross_contamination`, `test_no_model_migration_drift`)와 리뷰가 한다. 정적 체커는 값싸게 잡히는 냄새만 본다.
- **재생성물은 코드의 그림자.** `generated/` 를 손으로 고치지 말 것 — 다음 생성에 덮어쓰여진다.
- **동기화도 사람 게이트.** gardening 워크플로는 PR 만 연다(자동 머지 없음).
- 새 황금 원칙을 추가하면 `core-beliefs.md` 와 `golden-principles-check.ps1` 을 **함께** 갱신한다.
