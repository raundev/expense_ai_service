import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, Send, Loader2, Bot as BotIcon, FileText, Languages } from "lucide-react";
import { api, errMessage, unwrap, LLM_TIMEOUT_MS } from "../api";
import type { ApiResponse, BotResponse, PolicyChatResponse, ChatTranslateResponse } from "../types";

const BOTS_URL = "/api/v1/bots";
const CHAT_URL = "/api/v1/policies/chat";
const TRANSLATE_URL = "/api/v1/policies/chat/translate";

// '번역' 버튼 라벨을 질문 언어에 맞춘다(일본어→翻訳 / 한국어→번역 / 중국어→翻译 / 그 외→Translate).
// 백엔드 ChatService._detect_target_language 와 동일한 유니코드 스크립트 판정:
// 가나/한글은 즉시 확정하고, 한자는 가나·한글이 전혀 없을 때만 중국어로 본다.
function translateLabel(text: string): string {
  let hasCjk = false;
  for (const ch of text) {
    const o = ch.codePointAt(0) ?? 0;
    if (o >= 0x3040 && o <= 0x30ff) return "翻訳"; // 가나 → 일본어 확정
    if (o >= 0xac00 && o <= 0xd7a3) return "번역"; // 한글 → 한국어 확정
    if (o >= 0x4e00 && o <= 0x9fff) hasCjk = true; // 한자(가나/한글 없을 때만 중국어)
  }
  return hasCjk ? "翻译" : "Translate";
}

// 소스 번역 상태 — key=`${메시지인덱스}-${소스인덱스}`.
interface TranslationState {
  loading?: boolean;
  translated?: string;
  error?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: PolicyChatResponse["sources"];
}

// RAG 페이지 — 봇 선택 후 사내 규정 RAG 챗봇과 대화.
export default function RagPage() {
  const [bots, setBots] = useState<BotResponse[]>([]);
  const [botId, setBotId] = useState<string>("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [translations, setTranslations] = useState<Record<string, TranslationState>>({});
  const [query, setQuery] = useState("");
  const [loadingBots, setLoadingBots] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadBots = useCallback(async () => {
    setLoadingBots(true);
    setError(null);
    try {
      const { data } = await api.get<ApiResponse<BotResponse[]>>(BOTS_URL);
      const list = unwrap(data) ?? [];
      setBots(list);
      if (list.length && !botId) setBotId(list[0].id);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setLoadingBots(false);
    }
  }, [botId]);

  useEffect(() => {
    loadBots();
  }, [loadBots]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // 봇을 바꾸면 세션/대화 초기화.
  const onBotChange = (id: string) => {
    setBotId(id);
    setSessionId(null);
    setMessages([]);
    setTranslations({});
  };

  // 소스(규정 원문) 온디맨드 번역 — 답변(assistant) 메시지의 직전 사용자 질문 언어로 번역.
  const translateSource = async (msgIdx: number, srcIdx: number) => {
    const src = messages[msgIdx]?.sources?.[srcIdx];
    if (!src?.snippet || !botId) return;
    const key = `${msgIdx}-${srcIdx}`;
    const referenceQuery = messages[msgIdx - 1]?.content ?? "";
    setTranslations((t) => ({ ...t, [key]: { ...t[key], loading: true, error: undefined } }));
    try {
      const { data } = await api.post<ApiResponse<ChatTranslateResponse>>(
        TRANSLATE_URL,
        { bot_id: botId, text: src.snippet, reference_query: referenceQuery },
        { timeout: LLM_TIMEOUT_MS } // 번역도 RunPod LLM 호출이라 전역 60초로는 부족
      );
      const res = unwrap(data);
      setTranslations((t) => ({ ...t, [key]: { loading: false, translated: res.translated } }));
    } catch (e) {
      setTranslations((t) => ({ ...t, [key]: { loading: false, error: errMessage(e) } }));
    }
  };

  const send = async () => {
    const q = query.trim();
    if (!q || !botId) return;
    setSending(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setQuery("");
    try {
      const { data } = await api.post<ApiResponse<PolicyChatResponse>>(
        CHAT_URL,
        {
          bot_id: botId,
          query: q,
          session_id: sessionId,
          channel: "web",
        },
        { timeout: LLM_TIMEOUT_MS } // RunPod LLM 응답 대기(최대 150초) — 전역 60초로는 부족
      );
      const res = unwrap(data);
      setSessionId(res.session_id);
      setMessages((m) => [...m, { role: "assistant", content: res.answer, sources: res.sources }]);
    } catch (e) {
      setError(errMessage(e));
      setMessages((m) => [...m, { role: "assistant", content: `⚠️ ${errMessage(e)}` }]);
    } finally {
      setSending(false);
    }
  };

  const selectedBot = bots.find((b) => b.id === botId);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">RAG</h1>
          <p className="text-sm text-slate-500">봇을 선택해 사내 규정 기반 RAG 챗봇과 대화합니다(테넌트/봇 격리).</p>
        </div>
        <button
          onClick={loadBots}
          disabled={loadingBots}
          className="inline-flex items-center gap-2 bg-slate-700 hover:bg-slate-800 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md"
        >
          {loadingBots ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          봇 새로고침
        </button>
      </div>

      {/* 봇 선택 */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-wrap items-end gap-4">
        <label className="text-xs text-slate-500 flex flex-col gap-1 min-w-[260px]">
          <span className="flex items-center gap-1"><BotIcon size={14} /> 봇 선택</span>
          <select
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={botId}
            onChange={(e) => onBotChange(e.target.value)}
          >
            {bots.length === 0 && <option value="">(봇 없음 — Admin/문서에서 먼저 생성)</option>}
            {bots.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} {b.disabled ? "(비활성)" : ""} · {b.llm_model}
              </option>
            ))}
          </select>
        </label>
        {selectedBot && (
          <div className="text-xs text-slate-500 space-y-0.5">
            <div>모델 <span className="font-mono text-slate-700">{selectedBot.llm_model}</span> · top_k {selectedBot.top_k} · temp {selectedBot.llm_temperature}</div>
            <div>세션 <span className="font-mono text-slate-700">{sessionId ?? "(신규)"}</span></div>
          </div>
        )}
      </div>

      {error && <div className="bg-red-50 text-red-700 text-sm rounded-md p-3 border border-red-200">{error}</div>}

      {/* 대화 영역 */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col h-[480px]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <p className="text-sm text-slate-400 text-center mt-10">
              {selectedBot?.recommended_questions?.length
                ? "추천 질문을 누르거나 직접 입력해 보세요."
                : "질문을 입력해 대화를 시작하세요."}
            </p>
          )}
          {selectedBot?.recommended_questions?.length && messages.length === 0 ? (
            <div className="flex flex-wrap gap-2 justify-center">
              {selectedBot.recommended_questions.map((rq) => (
                <button
                  key={rq.id}
                  onClick={() => setQuery(rq.question)}
                  className="text-xs px-3 py-1.5 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200"
                >
                  {rq.question}
                </button>
              ))}
            </div>
          ) : null}

          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                {m.content}
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-slate-300/40 space-y-1">
                    {m.sources.map((s, si) => {
                      const tr = translations[`${i}-${si}`];
                      return (
                        <div key={si} className="text-xs text-slate-500 flex items-start gap-1">
                          <FileText size={12} className="mt-0.5 shrink-0" />
                          <div className="flex-1">
                            <span className="font-medium">{s.title ?? s.file_name ?? s.doc_id}</span>
                            {s.snippet ? ` — ${s.snippet}` : ""}
                            {s.snippet && (
                              <button
                                onClick={() => translateSource(i, si)}
                                disabled={tr?.loading}
                                className="ml-1.5 inline-flex items-center gap-0.5 align-baseline text-blue-600 hover:text-blue-700 disabled:opacity-50"
                              >
                                {tr?.loading ? (
                                  <Loader2 size={11} className="animate-spin" />
                                ) : (
                                  <Languages size={11} />
                                )}
                                {translateLabel(messages[i - 1]?.content ?? "")}
                              </button>
                            )}
                            {tr?.translated && (
                              <div className="mt-0.5 pl-2 border-l-2 border-blue-200 text-slate-600 whitespace-pre-wrap">
                                {tr.translated}
                              </div>
                            )}
                            {tr?.error && <div className="mt-0.5 text-red-500">{tr.error}</div>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-slate-100 rounded-2xl px-4 py-2.5"><Loader2 size={16} className="animate-spin text-slate-400" /></div>
            </div>
          )}
        </div>

        {/* 입력 */}
        <div className="border-t border-slate-200 p-3 flex gap-2">
          <input
            className="flex-1 border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder={botId ? "사내 규정에 대해 질문하세요..." : "먼저 봇을 선택하세요"}
            value={query}
            disabled={!botId || sending}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
          />
          <button
            onClick={send}
            disabled={!botId || sending || !query.trim()}
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-medium px-4 py-2 rounded-md"
          >
            <Send size={15} /> 전송
          </button>
        </div>
      </div>
    </div>
  );
}
