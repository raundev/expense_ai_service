"""사내 규정(RAG) 벡터 스토어 세팅 (11단계).

Qdrant 를 벡터 DB 로 사용한다. 모든 테넌트의 규정 청크를 단일 컬렉션
(`company_policies`) 에 저장하되, 회사/사업장 격리는 컬렉션 분리가 아니라
각 청크 payload 의 `metadata.company_id` / `metadata.workplace_id` 에 대한
Qdrant Payload Filter 로 수행한다 (실제 격리 검색 로직은 `policy_service` 참조).

임베딩기(OpenAIEmbeddings)와 ChatLLM 은 사내 GPU(RunPod) 프록시 및 사내 SSL
인터셉션 환경을 통과해야 하므로, `llm_recommender.py` 와 동일하게
`OPENAI_API_BASE`(커스텀 base_url) 와 `SSL_CERT_FILE`(사내 CA) 처리를 유지한다.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from app.core.config import settings

logger = logging.getLogger(__name__)

# 전 테넌트 공용 컬렉션. 격리는 payload filter 로 수행한다.
COLLECTION_NAME = "company_policies"


# ---------------------------------------------------------------------------- #
# Embeddings
# ---------------------------------------------------------------------------- #
class _LocalFastEmbedEmbeddings(Embeddings):
    """fastembed(TextEmbedding) 를 LangChain Embeddings 인터페이스로 감싼 로컬 임베딩기.

    외부 임베딩 API 없이 로컬 ONNX 모델로 임베딩한다(오프라인/사내망/로컬 테스트용).
    RunPod 처럼 임베딩 라우트가 없는 LLM 프록시 환경에서도 RAG/컴플라이언스를 돌릴 수 있다.
    """

    def __init__(self, model_name: str) -> None:
        # 사내 SSL 인터셉션 환경에서 모델 최초 다운로드가 httpx(= SSL_CERT_FILE 인식) 경로를
        # 타도록 HF Xet 전송 백엔드를 비활성화한다(Xet 은 SSL_CERT_FILE 을 무시함).
        # 모델이 캐시된 뒤에는 오프라인 로드라 무관하다.
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from fastembed import TextEmbedding  # lazy import (fastembed 미설치 환경 보호)

        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([text]))).tolist()


def build_policy_embeddings() -> Embeddings:
    """사내 규정 임베딩기 구성.

    `EMBEDDING_PROVIDER` 로 분기한다:
      * "fastembed" -> 로컬 ONNX 임베딩(_LocalFastEmbedEmbeddings). API/네트워크 불필요.
      * 그 외("openai") -> OpenAIEmbeddings. 커스텀 base_url(`OPENAI_API_BASE`) 적용 +
        사내 CA(`SSL_CERT_FILE`) 가 있으면 `verify=<CA>` 로 http_client 주입.
    """
    if settings.EMBEDDING_PROVIDER.lower() == "fastembed":
        logger.info("FastEmbed 로컬 임베딩 사용 (model=%s)", settings.EMBEDDING_MODEL)
        return _LocalFastEmbedEmbeddings(settings.EMBEDDING_MODEL)

    emb_kwargs: dict = {
        "api_key": settings.OPENAI_API_KEY,
        "base_url": settings.OPENAI_API_BASE,
        "model": settings.EMBEDDING_MODEL,
    }

    ssl_cert = os.environ.get("SSL_CERT_FILE")
    if ssl_cert and os.path.isfile(ssl_cert):
        import httpx

        emb_kwargs["http_client"] = httpx.Client(verify=ssl_cert, timeout=30.0)
        logger.info("OpenAIEmbeddings custom http_client 주입 (SSL CA: %s)", ssl_cert)

    return OpenAIEmbeddings(**emb_kwargs)


# ---------------------------------------------------------------------------- #
# Qdrant client / collection
# ---------------------------------------------------------------------------- #
def _build_client() -> QdrantClient:
    """`settings.QDRANT_URL` 로 Qdrant 클라이언트를 초기화한다.

    Docker/별도 설치 없이 로컬 테스트가 가능하도록 임베디드(local) 모드를 지원한다:
      * ``":memory:"``       -> 인메모리(휘발성) 임베디드. 프로세스 종료 시 소멸.
      * ``"path:<dir>"``     -> 로컬 폴더 영속 임베디드 (예: ``path:./qdrant_local``).
      * 그 외(``http(s)://``) -> 원격 Qdrant 서버 모드 (운영/Docker).

    주의: 임베디드 모드는 해당 폴더에 파일 락을 걸어 **한 번에 한 프로세스만** 연다
    (uvicorn 단일 워커면 무방).
    """
    url = settings.QDRANT_URL
    if url == ":memory:":
        return QdrantClient(location=":memory:")
    if url.startswith("path:"):
        return QdrantClient(path=url[len("path:") :])
    return QdrantClient(url=url, api_key=settings.QDRANT_API_KEY)


def _ensure_collection(client: QdrantClient, embeddings: Embeddings) -> None:
    """`company_policies` 컬렉션이 없을 경우에만 생성한다.

    벡터 차원은 임베딩 모델에 종속되므로(text-embedding-3-small=1536) 하드코딩하지
    않고 실제 임베딩 1회로 산출한다. 거리 함수는 QdrantVectorStore 기본값과 동일한
    COSINE 을 사용한다.
    """
    if client.collection_exists(COLLECTION_NAME):
        return

    dim = len(embeddings.embed_query("dimension probe"))
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )
    logger.info("Qdrant 컬렉션 생성: %s (dim=%d, COSINE)", COLLECTION_NAME, dim)


@lru_cache(maxsize=1)
def get_policy_vector_store() -> QdrantVectorStore:
    """`company_policies` 컬렉션에 연결된 QdrantVectorStore 싱글톤을 반환한다.

    클라이언트 연결 / 컬렉션 보장 / 임베딩 세팅은 프로세스 단위 1회만 수행한다
    (lru_cache). 매 요청마다 재연결하지 않는다.
    """
    client = _build_client()
    embeddings = build_policy_embeddings()
    _ensure_collection(client, embeddings)
    return QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=embeddings,
    )
