# Bizplay AI — 컴플라이언스 테스트 콘솔 (Frontend)

Phase 1 백엔드 API(영수증 추천 + RAG 컴플라이언스 감사)를 브라우저에서 종합 테스트하기 위한
경량 SPA 입니다. **Vite + React + TypeScript + Tailwind CSS**.

## 구조
- **진입 페이지(`/`)**: 테넌트 정보(회사 `X-Company-ID` / 사업장 `X-Workplace-ID`) + API Base URL(필수)과
  관리자/직원 ID(선택)를 입력하면 localStorage 에 저장되고 콘솔로 진입한다. axios 인터셉터가 모든 요청
  헤더에 자동 주입한다. 상단 "테넌트 변경" 으로 언제든 되돌아올 수 있다.
- **콘솔(`/console/*`)**: 좌측 사이드바 6개 메뉴(`react-router-dom` HashRouter).
  1. **영수증** — 단건 용도 추천(RULE→HISTORY→LLM) + 컴플라이언스 검사.
  2. **룰 조회** — 활성 분류 규칙 목록 조회 + 신규 등록 / 수정.
  3. **RAG** — 봇 선택 후 사내 규정 RAG 챗봇과 대화(세션·출처 표시, 추천 질문).
  4. **Document** — 공통 문서 모듈: 파일 업로드(비동기 임베딩)·텍스트 즉시 적재·목록·다운로드·삭제.
  5. **Compliance Admin** — KPI 대시보드 + 위반 그리드 + 소명(미요청→요청완료→정상처리/위반확정) 전이.
  6. **Admin** — 테넌트 화이트리스트 등록·상태(ACTIVE/SUSPENDED) 관리 + Soft Delete 물리 정리 워커 트리거.

## 로컬 실행
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```
> 백엔드를 함께 띄우세요: 프로젝트 루트에서 `uvicorn app.main:app --reload` (http://localhost:8000)
> 콘솔 상단 "API Base URL" 을 백엔드 주소로 맞추면 됩니다(기본 `http://localhost:8000`).

## 빌드
```bash
npm run build        # dist/ 생성 (Vite 기본 빌드)
npm run preview      # 빌드 결과 미리보기
```

## Vercel 배포
이 SPA 는 단일 라우트라 별도 `vercel.json` 설정이 필요 없습니다.
1. GitHub 저장소를 Vercel 에 연결(Import).
2. **Root Directory** 를 **`frontend`** 로 지정.
3. Framework Preset: **Vite** (자동 감지). Build Command `npm run build`, Output Directory `dist` (기본값).
4. Deploy 후, 배포된 페이지 상단 설정 패널의 **API Base URL** 을 실제 백엔드 주소로 입력하면 됩니다.

> 백엔드(FastAPI)는 CORS 가 모든 오리진을 허용하도록 설정되어 있어 Vercel/localhost 어디서든 호출 가능합니다.
> (단, 백엔드가 사내망 전용이면 브라우저에서 접근 가능한 위치에 백엔드가 노출되어 있어야 합니다.)
