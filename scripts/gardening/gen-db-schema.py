#!/usr/bin/env python
"""DB 스키마 자동 생성기 — SQLAlchemy 메타데이터에서 docs/generated/db-schema.md 를 만든다.

코드(모델)가 진실이고 문서는 그림자다. 이 스크립트가 그 그림자를 코드에 맞춘다(doc-gardening).
앱 풀스택이 있는 '시스템 python' 으로 실행한다(core-architecture.md §Python 레이아웃).

    python scripts/gardening/gen-db-schema.py
    python scripts/gardening/gen-db-schema.py --check   # 드리프트만 검사(쓰지 않음, 다르면 exit 1)

멀티테넌트 규약(GP-1): 대부분의 도메인 테이블엔 company_id/workplace_id 가 있어야 한다.
없으면 표 옆에 ⚠ 로 표시해 리뷰 신호를 남긴다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 앱 import 전에 안전한 기본 환경을 깐다(이 스크립트는 서버가 아니라 메타데이터만 읽는다).
os.environ.setdefault("ENVIRONMENT", "local")
# Windows 콘솔(cp949)에서 한글·기호(— 등) print 가 깨지지 않도록 stdout 을 UTF-8 로 강제.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # py3.7+
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "generated" / "db-schema.md"
sys.path.insert(0, str(ROOT))

TENANT_COLS = {"company_id", "workplace_id"}


def render() -> str:
    # app.models 를 import 하면 모든 모델이 Base.metadata 에 등록된다(app/models/__init__.py).
    from app.models import Base  # noqa: E402

    lines: list[str] = []
    lines.append("<!-- AUTO-GENERATED — 손으로 수정하지 말 것. 생성: python scripts/gardening/gen-db-schema.py -->")
    lines.append("# DB 스키마 (자동 생성)")
    lines.append("")
    lines.append("SQLAlchemy `Base.metadata` 에서 추출. ⚠ 는 멀티테넌트 컬럼(company_id/workplace_id) 누락 신호(GP-1).")
    lines.append("")

    for table in Base.metadata.sorted_tables:
        colnames = {c.name for c in table.columns}
        tenant_ok = TENANT_COLS.issubset(colnames)
        flag = "" if tenant_ok else "  ⚠ 테넌트 컬럼 없음"
        lines.append(f"## `{table.name}`{flag}")
        lines.append("")
        lines.append("| 컬럼 | 타입 | NULL | 키/비고 |")
        lines.append("|------|------|------|---------|")
        for col in table.columns:
            keys = []
            if col.primary_key:
                keys.append("PK")
            for fk in col.foreign_keys:
                keys.append(f"FK→{fk.target_fullname}")
            if col.index:
                keys.append("idx")
            if col.unique:
                keys.append("uniq")
            nullable = "Y" if col.nullable else "N"
            lines.append(f"| {col.name} | {col.type} | {nullable} | {', '.join(keys)} |")
        # 복합 인덱스
        if table.indexes:
            idx_desc = "; ".join(
                f"{ix.name}({', '.join(c.name for c in ix.columns)})" for ix in sorted(table.indexes, key=lambda i: i.name or "")
            )
            lines.append("")
            lines.append(f"_인덱스_: {idx_desc}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    content = render()
    check = "--check" in sys.argv
    if check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.strip() != content.strip():
            print(f"[gen-db-schema] DRIFT: {OUT} 가 모델과 다릅니다. `python scripts/gardening/gen-db-schema.py` 로 재생성하세요.")
            return 1
        print("[gen-db-schema] OK — 스키마 문서가 모델과 일치합니다.")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    print(f"[gen-db-schema] 생성 완료: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
