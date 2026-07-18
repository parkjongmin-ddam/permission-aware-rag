# STO Chapter — Integration & End-to-End Evaluation / STO 챕터 통합·종단 평가

The **STO legal chapter** (Korean token-security statutory reference, 96 documents adapted
from the sibling [`sto-rag`](https://github.com/parkjongmin-ddam/sto-rag) project) is
integrated into the corpus and served by the same permission engine as the BWCorp
fixtures. This note records how it maps onto the permission model and the end-to-end
verification results.

> **STO 법령 챕터**(토큰증권 법령 참조, sto-rag에서 가져온 96문서)를 코퍼스에 통합해 BWCorp
> 픽스처와 동일한 권한 엔진으로 서빙합니다. 권한 모델 매핑과 종단 검증 결과를 정리합니다.

## Mapping / 매핑

STO uses domain-view tiers `{general, legal, engineer}`; permission here is keyed on
`sensitivity`, so the tiers map onto that axis (`scripts/adapt_sto_chapter.py`):

| STO tier | → `sensitivity` | Readable by / 열람 |
|---|---|---|
| general · legal (statute, summary, definition) | `public` | all RBAC roles / 전 역할 |
| engineer (engineering notes, open issues) | `internal` | team_lead and above / team_lead 이상 |

STO documents are `legal.regulatory` / `legal.opinion`, on which `parties_rule` abstains
(it only closes `legal.contract` / `legal.litigation`), so they fall through to
`sensitivity_rule` — the intended gate.

> STO는 뷰 티어 `{general, legal, engineer}`를 쓰고, 이 프로젝트 권한은 `sensitivity` 기준이라
> 티어를 그 축에 매핑합니다. STO는 `legal.regulatory/opinion`이라 `parties_rule`이 abstain →
> `sensitivity_rule`로 결정됩니다.

## End-to-end verification / 종단 검증

Full stack — BGE-M3 embeddings → pgvector (HNSW) → permission filter → BGE reranker →
Claude generation — ingested with 141 documents (45 BWCorp + 96 STO) and queried live.

**The headline claim, proven on the STO chapter:** for the same query, an unauthorized
document never reaches the LLM. Query: *"증권성 판단의 엔지니어링 관점과 미해결 이슈"*
(targets the `internal` engineer notes STO-009 / STO-010):

| Persona | Retrieved (`/query`) | LLM context (`/answer`) | Answer |
|---|---|---|---|
| `employee` | public STO only — **STO-009/010 never surface** | public STO only | "engineering perspective not in the provided documents" (cannot cite internal) |
| `team_lead` | includes STO-009/010 | includes STO-009/010 | answers the engineering perspective, cites `[STO-009] [STO-010]` |

The internal documents are filtered **before ranking and before generation**, so the
employee's model literally never sees them — no post-filter leakage, and the answer
differs by permission, not by prompt.

> **헤드라인 주장을 STO로 실증:** 같은 질의라도 미인가 문서는 LLM에 도달하지 않습니다. employee는
> internal STO-009/010이 검색·context 어디에도 안 나와 "엔지니어링 관점은 제공 문서에 없다"고
> 답하고, team_lead만 STO-009/010을 받아 인용합니다. 권한 필터가 랭킹·생성 *이전*에 작동합니다.

### Retrieval metrics / 검색 지표

`scripts/eval_retrieval.py` over the labelled set (BWCorp + STO, 41 permission-eligible
cases; ground truth = the real `can_read` policy):

| metric | w/o rerank | w/ rerank | Δ |
|---|---|---|---|
| precision@5 | 0.356 | **0.411** | +0.055 |
| recall@5 | 0.949 | 0.947 | −0.002 |
| F1 | 0.518 | **0.573** | +0.055 |

The reranker consistently improves precision.

### Measurement caught a mislabeled case / 측정이 잡아낸 라벨 오류

An earlier `TC-STO-03` showed precision@5 = 0.00 and looked like a retrieval gap. On
inspection it was a **mislabeled ground truth**, not a retrieval failure: the query
*"계좌관리기관 자격 요건"* (qualification requirements) is answered by the **statute**
(전자등록법 제19조 — "다음 각 호의 어느 하나에 해당하는 자는 계좌관리기관이 될 수 있다",
STO-075…083 + the definition STO-091), which BGE-M3 retrieved correctly all along — the
gold had been set to the *concept* entry docs (STO-016/017/018) instead. After correcting
the gold to the statute chunks, **precision@5 = 1.00** (every top-5 result is a correct
qualification-statute doc; recall@5 = 0.45 is bounded by top_k=5 vs 11 relevant chunks).

> 초기 `TC-STO-03`은 precision@5=0.00으로 검색 갭처럼 보였으나, 실제로는 **ground truth 라벨
> 오류**였습니다. "자격 요건" 질의의 정답은 조문(제19조 = "…에 해당하는 자는 계좌관리기관이 될 수
> 있다")인데 gold를 개념 entry(016/017/018)로 잘못 달았던 것 — BGE-M3는 조문을 정확히 회수하고
> 있었습니다. gold를 조문으로 교정하니 **precision@5=1.00**(recall@5=0.45는 관련 11문서 대비
> top-5 상한). 측정이 아니었으면 못 잡았을, 카파시 "측정 후 판단"의 사례.

## Reproduce / 재현

```bash
docker compose up -d                        # pgvector (HNSW schema via init.sql)
uv run python scripts/adapt_sto_chapter.py  # data/sto_chapter.yaml (from sto-rag)
uv run python scripts/ingest.py             # 141 docs → pgvector (BGE-M3, ~2GB first run)
uv run uvicorn permission_aware_rag.main:app # server (loads BGE reranker)
uv run python scripts/eval_retrieval.py     # precision/recall incl. STO cases
```

Permission-level checks need no DB/models: `uv run pytest tests/test_sto_chapter.py
tests/test_sto_eval.py`.
