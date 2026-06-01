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
def build_policy_embeddings() -> Embeddings:
    """사내 규정 임베딩기(OpenAIEmbeddings) 구성.

    `.env` 의 `EMBEDDING_MODEL`(기본: text-embedding-3-small) 을 사용한다.
    `llm_recommender.py` 와 동일하게 커스텀 base_url(`OPENAI_API_BASE`) 을 적용하고,
    사내 CA(`SSL_CERT_FILE`) 가 있으면 `verify=<CA>` 로 http_client 를 주입하여
    회사 SSL 인터셉션을 통과시킨다.
    """
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
    """`settings.QDRANT_URL` 로 Qdrant 클라이언트를 초기화한다."""
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)


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
