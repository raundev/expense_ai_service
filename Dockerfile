# syntax=docker/dockerfile:1
# 프로덕션 배포용 이미지 (Bizplay AI Compliance & Recommendation API)
FROM python:3.12-slim

# 캐시 최소화 + 버퍼링 해제 (로그 즉시 출력)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) 의존성만 먼저 설치 -> 소스 변경 시에도 의존성 레이어 캐시 재사용
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 2) 애플리케이션 소스 복사 (.dockerignore 로 .env/venv/*.db 등 제외)
COPY . .

# 3) 보안: 비루트(non-root) 사용자로 실행 + 데이터(SQLite/볼륨) 디렉터리 권한 부여
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 기동 시 DB 마이그레이션(head)을 적용한 뒤 서버를 실행한다.
# (alembic 콘솔 스크립트는 cwd 를 sys.path 에 넣지 않아 로컬 alembic/ 디렉터리에
#  가려지지 않으며, env.py 가 런타임에 프로젝트 루트를 path 에 추가한다.)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
