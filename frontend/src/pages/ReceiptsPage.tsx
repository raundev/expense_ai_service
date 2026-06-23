import SingleRecommendTab from "../components/SingleRecommendTab";

// 영수증 메뉴 — 영수증 단건 용도 추천 + 컴플라이언스 검사(기존 컴포넌트 재사용).
export default function ReceiptsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">영수증</h1>
        <p className="text-sm text-slate-500">영수증 1건의 용도 분류(RULE→HISTORY→LLM)와 사칙 컴플라이언스 검사를 실행합니다.</p>
      </div>
      <SingleRecommendTab />
    </div>
  );
}
