# generated/ — 자동 생성 산출물 (DO NOT EDIT BY HAND)

이 디렉터리의 파일은 **도구가 생성**한다. 손으로 고치지 말 것 — 다음 생성 때 덮어쓰여진다.
코드가 진실이고, 이 문서는 코드의 *그림자*다. 어긋나면 doc-gardening 이 재생성한다.

| 파일 | 생성기 | 무엇 |
|------|--------|------|
| [db-schema.md](db-schema.md) | `python scripts/gardening/gen-db-schema.py` | SQLAlchemy 메타데이터에서 추출한 테이블/컬럼 스키마 |

## 재생성
```powershell
python scripts/gardening/gen-db-schema.py   # docs/generated/db-schema.md 갱신
```
CI/doc-gardening 은 이 생성기를 돌려 결과가 커밋본과 다르면(=드리프트) 동기화 PR 을 제안한다.
