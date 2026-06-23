---
title: <한 줄 제목>
slug: <kebab-case-슬러그>
status: active        # active | blocked | done | abandoned
owner: <에이전트/사람>
created: YYYY-MM-DD
updated: YYYY-MM-DD
related_gp: []        # 영향받는 황금 원칙, 예: [GP-1, GP-5]
---

# <제목>

## 1. 목표 (왜)
<이 작업이 끝나면 무엇이 참이 되는가. 측정 가능한 완료 조건.>

## 2. 배경 / 제약
<관련 설계 문서 링크. 건드리면 안 되는 불변식(GP-N). 알려진 함정.>

## 3. 계획 (무엇을, 순서대로)
- [ ] 단계 1 — …
- [ ] 단계 2 — …
- [ ] 검증 — `python -m pytest ...` / 관측 하네스로 확인

## 4. 검증 전략
<어떤 테스트/스냅샷/쿼리로 "됐다"를 증명하는가. 자가 검증 가능해야 한다.>

## 5. 진행 로그 (append-only)
- YYYY-MM-DD: <무엇을 했고 무엇을 배웠나>

## 6. 완료 요약 (status=done 시 작성)
<최종 상태, 남은 후속 작업(있으면 tech-debt-ledger 로), 관련 PR/커밋.>
