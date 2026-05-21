# syntax=docker/dockerfile:1

FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

ENV HF_HOME=/home/user/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/user/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/user/.cache/huggingface

WORKDIR /home/user/app

RUN pip install --no-cache-dir --user \
        torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir --user \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.30" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.5" \
        "psycopg[binary,pool]>=3.2" \
        "pgvector>=0.3" \
        "sentence-transformers>=3.0" \
        "pyyaml>=6.0" \
        "pyjwt>=2.10"

COPY --chown=user:user src/ ./src/
COPY --chown=user:user pyproject.toml ./
COPY --chown=user:user README.md ./

RUN pip install --no-cache-dir --user --no-deps -e .

ENV API_PORT=7860 \
    API_HOST=0.0.0.0 \
    ENVIRONMENT=production

EXPOSE 7860

CMD ["uvicorn", "permission_aware_rag.main:app", "--host", "0.0.0.0", "--port", "7860"]
