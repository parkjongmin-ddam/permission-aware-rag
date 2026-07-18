# permission-aware-rag

**Permission-aware Retrieval-Augmented Generation for enterprise / air-gapped environments — access control is enforced at the *retrieval* stage, before any document ever reaches the LLM.**

> 권한 인식 RAG. 문서가 LLM에 도달하기 *이전*, 검색(retrieval) 단계에서 접근 제어를 강제합니다. 사내·망분리(air-gapped) 환경을 염두에 두고 설계했습니다.

![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.13x-009688)
![pgvector](https://img.shields.io/badge/pgvector-HNSW-336791)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Why permission-aware? / 왜 권한 인식 RAG인가

A normal RAG system retrieves the most *similar* chunks and feeds them to the LLM. In an enterprise that means an employee can surface a document they should never see — the model will happily summarize a confidential litigation memo if it is semantically relevant to the question.

> 일반 RAG는 *유사도*가 높은 청크를 그대로 LLM에 넣습니다. 사내 환경에서는 직원이 봐서는 안 될 문서가 검색되어 그대로 요약될 수 있습니다. "내용이 질문과 관련 있으니까" 기밀 소송 메모도 그대로 답변에 섞입니다.

This project moves access control **left** — the permission decision happens during retrieval, so denied documents are never passed to the model and never appear in the answer or its citations.

> 이 프로젝트는 접근 제어를 **앞단으로** 옮깁니다. 권한 판단을 검색 단계에서 수행하므로, 거부된 문서는 애초에 모델로 전달되지 않고 답변·인용에도 등장하지 않습니다.

Two layers work together:

> 두 개의 레이어가 함께 동작합니다:

- **ReBAC (Relationship-Based Access Control)** — can this user see this document *because of their relationship to it* (project member, named party, incident stakeholder, the subject themselves)?
- **Privilege / sensitivity gating** — even a high-clearance role (e.g. an auditor) can be blocked from specific privileged documents.

> - **ReBAC(관계 기반 접근 제어)** — 사용자가 문서와 *맺은 관계*(프로젝트 멤버, 명시된 당사자, 인시던트 이해관계자, 본인) 때문에 볼 수 있는가?
> - **권한/민감도 게이팅** — 높은 권한(예: 감사인)이라도 특정 특권 문서는 차단될 수 있습니다.

---

## Architecture / 아키텍처

This is an **explicit function pipeline**, not a graph/agent framework. The flow is deterministic and easy to debug, trace, and audit — which is exactly what an access-control system should be.

> 그래프/에이전트 프레임워크가 아니라 **명시적 함수 파이프라인**입니다. 흐름이 결정적(deterministic)이라 디버깅·추적·감사가 쉽습니다. 접근 제어 시스템에 요구되는 성질입니다.

```
                ┌─────────────┐
   query  ──▶   │  retrieval  │  BGE-M3 embedding → pgvector (HNSW) top-k
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │  permission │  6 rules → allowed_doc_ids / denied_doc_ids
                │   filter    │  (ReBAC + sensitivity)
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │  reranking  │  BGE Reranker v2-m3 on the *allowed* set
                └──────┬──────┘
                       ▼
                ┌─────────────┐
                │ generation  │  Claude (ChatAnthropic) — swappable with Ollama
                └──────┬──────┘
                       ▼
              answer + cited docs + audit log
```

**Retrieval → Permission → Rerank → Generation.** Denied documents are dropped *before* reranking and generation. Every request is written to an audit log with the allowed/denied document IDs.

> **검색 → 권한 → 리랭킹 → 생성.** 거부 문서는 리랭킹·생성 *이전*에 제거됩니다. 모든 요청은 allowed/denied 문서 ID와 함께 감사 로그에 기록됩니다.

---

## The 6 permission rules / 6개 정책 룰

Rules are evaluated in order (defined in `permission/policy.py`). The first rule that grants access wins; otherwise the document is denied.

> 룰은 정해진 순서(`permission/policy.py`)로 평가됩니다. 접근을 허용하는 첫 룰이 적용되며, 없으면 거부됩니다.

| Rule | Grants access when… / 허용 조건 |
| --- | --- |
| `self_access_rule` | The user *is* the subject of the document / 사용자가 문서의 당사자 본인 |
| `project_rule` | The user is a member of the document's project / 문서 프로젝트의 멤버 |
| `parties_rule` | The user is listed in the document's `parties` / 문서 `parties`에 명시됨 |
| `incident_rule` | The user is a stakeholder of the incident / 인시던트 이해관계자 |
| `audit_rule` | The user has an audit role (with sensitivity limits) / 감사 권한(민감도 한도 적용) |
| `sensitivity_rule` | Default gate by document sensitivity vs. role clearance / 문서 민감도 대비 역할 권한 기본 게이트 |

---

## The 3-persona demo / 3인 페르소나 데모

The same query, three users — the answer changes because the *visible document set* changes. This is the core of the demo (9 personas total are defined; these three make the contrast clearest).

> 같은 질문, 세 사용자 — *볼 수 있는 문서 집합*이 달라지므로 답변이 달라집니다. 총 9개 페르소나 중 대비가 가장 뚜렷한 3개입니다.

| Persona | Allowed / Denied | DOC-044 (privileged litigation memo) | Resulting answer / 결과 |
| --- | --- | --- | --- |
| **`emp_001`** (general employee) | 2 / 13 | denied | "관련 소송 정보 없음" — sees almost nothing |
| **`aud_001`** (auditor) | 13 / 2 | **denied** | Broad visibility, **but still blocked** from the privileged doc |
| **`exec_001`** (executive) | 9 / 6 | **cited** | Full litigation details (incl. the case amount) via `parties_rule` |

The key point: the **auditor sees more documents than the employee (13 vs 2)** yet **both are blocked from DOC-044** — demonstrating that ReBAC + privilege gating beats role-based access control alone. "More senior" ≠ "sees everything."

> 핵심: **감사인이 직원보다 더 많은 문서(13 vs 2)를 보지만**, **둘 다 DOC-044는 차단**됩니다. 단순 RBAC만으로는 불가능한, "ReBAC + 권한 게이팅"의 가치를 보여줍니다. "직급이 높다 = 다 본다"가 아닙니다.

---

## Tech stack / 기술 스택

| Layer | Choice |
| --- | --- |
| Language / runtime | Python 3.13, managed with **uv** |
| API | FastAPI + uvicorn |
| Vector DB | PostgreSQL + **pgvector** (HNSW index, `vector(1024)`) |
| Embedding | **BGE-M3** (1024-dim, cross-lingual KO/EN) via sentence-transformers |
| Reranker | **BGE Reranker v2-m3** |
| LLM (generation) | **Claude** via `langchain-anthropic` — *single swap point* for Ollama |
| Auth | JWT (PyJWT); mock token issuance per persona |
| Config | pydantic-settings (`.env`) |
| Observability (optional) | Langfuse — no-op without keys |

> 임베딩/리랭커는 BGE-M3 / BGE Reranker v2-m3, 벡터 DB는 pgvector(HNSW, 1024차원), 생성은 Claude(`langchain-anthropic`)이며 Ollama로 교체 가능한 단일 지점이 있습니다.

---

## Project structure / 프로젝트 구조

```
permission-aware-rag/
├── src/permission_aware_rag/   # application package
│   ├── main.py                 #   FastAPI app, router registration, CORS
│   ├── config.py               #   pydantic-settings (env vars, deploy mode)
│   ├── api/routes/             #   health, auth, query, answer
│   ├── auth/                   #   jwt_utils, dependencies, personas (9)
│   ├── permission/             #   rules.py (6 rules), policy.py, types.py
│   ├── retrieval/              #   embedder, reranker, retriever
│   ├── generation/             #   answerer.py  ← LLM swap point (Claude/Ollama)
│   ├── observability/          #   tracing.py (Langfuse, optional)
│   ├── audit/                  #   log.py
│   └── db/                     #   session.py (Postgres pool)
├── data/                       # demo document corpus
├── docker/postgres/            # pgvector init schema / SQL
├── demo/                       # interactive chat UI (persona buttons + chips)
├── eval/                       # RAGAS evaluation set + results
├── scripts/                    # ingest / eval harness / diagnostics
├── notebooks/                  # learning notebooks (e.g. LangGraph quickstart)
├── tests/                      # test suite
├── .github/workflows/          # CI (HF Space deploy workflow — see note below)
├── docker-compose.yml          # pgvector/pgvector:pg17
├── Dockerfile                  # python:3.13-slim
├── pyproject.toml              # hatchling, src layout
├── uv.lock
├── .env.example
└── LICENSE                     # MIT
```

> The core RAG pipeline is a plain function pipeline — the `notebooks/` LangGraph quickstart is a separate learning artifact, not part of the request path. / 핵심 RAG 파이프라인은 함수 파이프라인입니다. `notebooks/`의 LangGraph 퀵스타트는 별개의 학습용 자료로, 요청 경로와 무관합니다.

---

## Prerequisites / 사전 요구사항

- **Docker Desktop** (for the pgvector container) / pgvector 컨테이너용
- **Python 3.13** + [**uv**](https://github.com/astral-sh/uv) / 의존성 관리
- **Anthropic API key** — required only for the `/answer` endpoint (generation). `/query` works without it. / `/answer`(생성)에만 필요하며 `/query`는 없이 동작

> First model download (BGE-M3 + reranker) pulls ~2–3 GB and runs on CPU. The first request is slow; subsequent ones are cached. / 최초 1회 BGE-M3·리랭커 다운로드(~2~3GB, CPU 동작)로 첫 요청은 느리고 이후 캐시됩니다.

---

## Quickstart (local) / 빠른 시작 (로컬)

> Tested locally with Docker pgvector. Cloud/web deployment is **not** included here (the local pipeline is the supported path). / 로컬 Docker pgvector 기준으로 검증했습니다. 클라우드/웹 배포는 포함하지 않습니다(로컬 파이프라인이 지원 경로).

### 1. Clone & install / 클론 및 설치

```bash
git clone https://github.com/parkjongmin-ddam/permission-aware-rag.git
cd permission-aware-rag
uv sync          # creates .venv and installs from pyproject.toml
```

### 2. Configure environment / 환경 변수 설정

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# Postgres / pgvector (matches docker-compose.yml)
DATABASE_URL=postgresql://pawrag_user:pawrag_password@localhost:5432/permission_aware_rag

# Required for /answer (generation). /query works without it.
ANTHROPIC_API_KEY=sk-ant-...

# Local development
ENVIRONMENT=development

# Optional — Langfuse tracing (leave blank to disable; runs as no-op)
# LANGFUSE_PUBLIC_KEY=
# LANGFUSE_SECRET_KEY=
# LANGFUSE_HOST=https://cloud.langfuse.com
```

> ⚠️ Check these keys against your own `.env.example` — your file is the source of truth. / 위 키 이름은 본인 `.env.example`과 대조해 주세요. 실제 파일이 기준입니다.

### 3. Start the database / 데이터베이스 실행

```bash
docker compose up -d
docker compose ps            # wait for (healthy)
```

Verify schema & pgvector / 스키마·확장 확인:

```bash
docker compose exec postgres psql -U pawrag_user -d permission_aware_rag -c "\dt"
docker compose exec postgres psql -U pawrag_user -d permission_aware_rag -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
```

### 4. Load the demo documents / 데모 문서 적재

Embed the demo corpus (`data/documents.yaml`, 45 documents) into pgvector with BGE-M3. The first run downloads the model (~2 GB) and is cached afterward.

> `data/documents.yaml`의 45개 데모 문서를 BGE-M3로 임베딩해 pgvector에 적재합니다. 최초 1회 모델 다운로드(~2GB) 후 캐시됩니다. 재실행은 UPSERT라 안전합니다.

```bash
uv run python scripts/ingest.py
```

Expected output / 기대 출력:

```
Loaded 45 documents
Generated 45 embeddings, shape=(45, 1024)
Inserted/updated: 45
Failed: 0
Total in DB: 45
```

Verify the load / 적재 확인:

```bash
docker compose exec postgres psql -U pawrag_user -d permission_aware_rag \
  -c "SELECT sensitivity, COUNT(*) FROM documents GROUP BY sensitivity ORDER BY sensitivity;"
# public 7 / internal 12 / restricted 23 / privileged 3  (total 45)
```

### 5. Run the API / API 실행

```bash
uv run uvicorn permission_aware_rag.main:app --reload --port 8000
```

Open the interactive docs / Swagger 문서: **http://127.0.0.1:8000/docs**

### 6. Try the demo UI / 데모 UI

Open the chat UI in `demo/` in a browser (it calls the local API). Pick a persona, click a suggestion chip, and watch the **allowed / denied** badges and cited-document chips change per persona.

> `demo/` 폴더의 채팅 UI를 브라우저로 열면 로컬 API를 호출합니다. 페르소나를 고르고 추천 칩을 누르면 페르소나별로 **allowed/denied** 배지와 인용 문서 칩이 달라집니다.

---

## API / 엔드포인트

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`  | `/health` | Liveness check / 헬스체크 |
| `POST` | `/auth`   | Issue a JWT for a persona / 페르소나 JWT 발급 |
| `POST` | `/query`  | Retrieve + permission-filter (no LLM) / 검색 + 권한 필터(LLM 미사용) |
| `POST` | `/answer` | Full RAG: filtered retrieval → Claude answer / 풀 RAG: 필터 검색 → Claude 답변 |

A typical flow: `POST /auth` to get a persona token → call `/query` or `/answer` with that token. The response surfaces `allowed_doc_ids` and `denied_doc_ids` so you can *see* what the permission layer blocked.

> 일반 흐름: `/auth`로 페르소나 토큰 발급 → 해당 토큰으로 `/query`나 `/answer` 호출. 응답에 `allowed_doc_ids` / `denied_doc_ids`가 담겨 권한 레이어가 무엇을 막았는지 *눈으로* 확인할 수 있습니다.

---

## On-prem / air-gapped deployment / 온프레미스·망분리 전환

This project targets environments where external LLM calls and data exfiltration are controlled (network isolation, DLP, API-key governance). Generation is the **only** component that calls an external API, and it is isolated to a single swap point.

> 외부 LLM 호출과 데이터 유출이 통제되는 환경(망분리·DLP·API 키 거버넌스)을 겨냥합니다. 외부 API를 호출하는 부분은 생성(generation) 하나뿐이며, 단일 지점으로 격리되어 있습니다.

In `generation/answerer.py`, swap `ChatAnthropic` for `ChatOllama` to run fully on-premises with a local model. Embedding, reranking, retrieval, and permission enforcement are already local.

> `generation/answerer.py`에서 `ChatAnthropic`을 `ChatOllama`로 교체하면 로컬 모델로 완전 온프레미스 동작이 가능합니다. 임베딩·리랭킹·검색·권한 강제는 이미 로컬에서 수행됩니다.

| Mode | Embedding/Rerank | Generation |
| --- | --- | --- |
| Cloud demo | local (BGE) | Claude API |
| Air-gapped / API-restricted | local (BGE) | local Ollama |

---

## Evaluation / 평가

Retrieval quality was measured with RAGAS; adding the BGE reranker improved F1 by ~21% over the no-rerank baseline on the demo evaluation set.

> 검색 품질은 RAGAS로 측정했으며, BGE 리랭커 적용 시 무리랭커 베이스라인 대비 데모 평가셋에서 F1 약 21% 향상을 확인했습니다.

---

## Status / 현황

- ✅ Local pipeline (retrieval → permission → rerank → generation) working end-to-end
- ✅ 9 personas, 6 permission rules, 3-persona comparison demo
- ✅ `chat.html` local demo UI
- ✅ RAGAS evaluation (reranker uplift)
- ✅ STO legal chapter (96 docs, adapted from the sibling [`sto-rag`](https://github.com/parkjongmin-ddam/sto-rag) project) integrated — permission enforcement verified end-to-end through retrieval **and** generation; see [`docs/sto-chapter-eval.md`](docs/sto-chapter-eval.md)
- ➖ HF Spaces deploy workflow exists under `.github/workflows`, but no public deployment is maintained (local is the supported path)

> 로컬 파이프라인 전 구간 동작 / 9 페르소나·6룰·3인 데모 / 데모 UI / RAGAS 평가 완료 / STO 법령 챕터(96문서) 통합 — 검색·생성 종단에서 권한 강제 검증([`docs/sto-chapter-eval.md`](docs/sto-chapter-eval.md)). HF Spaces 배포 워크플로는 `.github/workflows`에 있으나 운영 중인 공개 배포는 없습니다(로컬이 지원 경로).

---

## License / 라이선스

MIT — see [LICENSE](./LICENSE).