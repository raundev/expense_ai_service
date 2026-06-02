# Bizplay AI — 컴플라이언스 테스트 콘솔 (Frontend)

Phase 1 백엔드 API(영수증 추천 + RAG 컴플라이언스 감사)를 브라우저에서 종합 테스트하기 위한
경량 SPA 입니다. **Vite + React + TypeScript + Tailwind CSS**.

## 기능
- **전역 설정**: API Base URL + 멀티테넌트 헤더(`X-Company-ID` / `X-Workplace-ID` / `X-Admin-ID` / `X-Employee-ID`)
  를 입력하면 axios 인터셉터가 모든 요청에 자동 주입(브라우저 localStorage 에 저장).
- **Tab 1 — 단건 추천 & 감사**: 영수증 1건을 입력해 용도 분류 + 컴플라이언스(준수/위반/사유) 확인.
- **Tab 2 — 컴플라이언스 대시보드**: KPI 카드(전체 탐지/미요청/요청완료/정상처리/위반확정) + 위반 그리드.
  각 행에서 **소명 요청 → 취소 / 처리(정상·위반)** 상태 전이를 직접 실행하며, 액션 후 KPI·그리드 자동 새로고침.

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
