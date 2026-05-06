# permission-aware-rag

> Permission-aware RAG with LangGraph for enterprise document search

![Status](https://img.shields.io/badge/status-WIP-orange)
![Python](https://img.shields.io/badge/python-3.13-blue)
![License](https://img.shields.io/badge/license-MIT-green)

엔터프라이즈 환경에서 사용자의 IAM 권한(역할·속성)에 따라 검색 가능한 문서 범위가 동적으로 달라지는, LangGraph 기반 멀티에이전트 RAG 시스템.

## 왜 이 프로젝트인가

엔터프라이즈 인증 인프라(ADFS, SAML, OIDC)를 다년간 운영하며 관찰한 한 가지 공백 — 대부분의 RAG 레퍼런스 구현은 *"누구나 모든 문서를 검색할 수 있다"*는 가정 위에서 동작합니다. 실제 기업 환경에서는 사용자의 역할(role)과 속성(attribute)에 따라 접근 가능한 문서가 달라야 하고, 이 차이가 검색 결과·답변 품질·감사 로그에 모두 반영되어야 합니다.

이 프로젝트는 그 공백을 메우기 위한 실험입니다. ReBAC·ABAC 같은 IAM 권한 모델을 RAG 파이프라인에 통합하는 다양한 방식(메타데이터 사전 필터링, 검색 후 필터링, 권한 가중치 반영)을 직접 구현·측정·비교합니다.
> **참고**: 본 프로젝트는 가상의 회사 "BWCorp"를 시나리오로 사용하며, IdP는 FastAPI 기반 mock JWT issuer로 시뮬레이션합니다. 실제 IdP 통합(Keycloak)은 M4의 stretch goal로 다룹니다. 실 ADFS/AD 인프라 구축은 본 프로젝트의 RAG 본질을 흐리고 시간 비용 대비 효용이 낮다고 판단해 의도적으로 제외했습니다.

## System Architecture

```mermaid
flowchart TD
    User([User])
    User -->|POST /query + JWT| FastAPI[FastAPI Gateway]
    FastAPI --> Auth
    Answer -->|answer + citations<br/>or refusal| User
    
    subgraph LangGraph["LangGraph Agent"]
        direction TB
        Auth["🔐 Auth Node"] -->|user_ctx| QR["✏️ Query Rewrite Node"]
        QR -->|rewritten_query| Retrieval["🔍 Retrieval Node"]
        Retrieval -->|candidate_docs| Rerank["📊 Re-ranking Node"]
        Rerank -->|ranked_docs| Answer["💬 Answer Node"]
    end
    
    Mock["Mock JWT Issuer"] -.->|verify keys| Auth
    LLM["LLM API"] -.-> QR
    LLM -.-> Answer
    PG[("pgvector<br/>+ permission metadata")] -.-> Retrieval
    BGE["BGE Reranker v2-m3"] -.-> Rerank
    
    Audit["📝 Audit Logger"]
    Auth -.-> Audit
    QR -.-> Audit
    Retrieval -.-> Audit
    Rerank -.-> Audit
    Answer -.-> Audit
    
    classDef nodeStyle fill:#dbeafe,stroke:#1e40af,stroke-width:2px,color:#1e3a8a
    classDef externalStyle fill:#f3f4f6,stroke:#6b7280,stroke-width:1px,stroke-dasharray:5 5,color:#374151
    classDef auditStyle fill:#fed7aa,stroke:#c2410c,stroke-width:2px,color:#7c2d12
    classDef userStyle fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    
    class Auth,QR,Retrieval,Rerank,Answer nodeStyle
    class Mock,LLM,PG,BGE externalStyle
    class Audit auditStyle
    class User,FastAPI userStyle
```

LangGraph 기반 멀티에이전트 구성:
- **Auth Node** — JWT 검증, 사용자 역할·속성 추출
- **Query Rewrite Node** — 권한 컨텍스트를 반영한 쿼리 재작성
- **Retrieval Node** — Vector DB에서 권한 메타데이터 필터링 + 의미검색
- **Re-ranking Node** — BGE Reranker 기반 권한·관련도 종합 점수
- **Answer Node** — Citation 포함 답변 생성, 권한 부족 시 거부 응답

> 모든 노드의 입출력은 별도의 **Audit Logger**에 기록되어 권한 추적과 사후 감사를 지원합니다 (다이어그램 단순화를 위해 생략).

LangGraph 기반 멀티에이전트 구성:
- **Auth Node** — JWT 검증, 사용자 역할·속성 추출
- **Query Rewrite Node** — 권한 컨텍스트를 반영한 쿼리 재작성
- **Retrieval Node** — Vector DB에서 권한 메타데이터 필터링 + 의미검색
- **Re-ranking Node** — BGE Reranker 기반 권한·관련도 종합 점수
- **Answer Node** — Citation 포함 답변 생성, 권한 부족 시 거부 응답
- **Audit Logger** — 모든 검색·답변 감사 로그

LangGraph 기반 멀티에이전트 구성:

- **Auth Node** — JWT 검증, 사용자 역할·속성 추출
- **Query Rewrite Node** — 권한 컨텍스트를 반영한 쿼리 재작성
- **Retrieval Node** — Vector DB에서 권한 메타데이터 필터링 + 의미검색
- **Re-ranking Node** — BGE Reranker 기반 권한·관련도 종합 점수
- **Answer Node** — Citation 포함 답변 생성, 권한 부족 시 거부 응답
- **Audit Logger** — 모든 검색·답변 감사 로그

## Tech Stack

- **Language**: Python 3.13
- **Backend**: FastAPI, LangGraph, LangChain
- **Vector DB**: pgvector (primary), Qdrant (comparison experiment)
- **Re-ranker**: BGE Reranker v2-m3
- **Tracing**: Langfuse or LangSmith
- **Infra**: AWS ECS Fargate, RDS PostgreSQL, S3
- **CI/CD**: GitHub Actions

## Roadmap

- [ ] **M1: Foundation** (~2주차) — repo 셋업, 시스템 설계, BWCorp 시나리오·데이터 스펙, LangGraph 기초
- [ ] **M2: MVP** (~4주차) — FastAPI + pgvector + JWT 인증 + 권한 필터링 + LangGraph 3노드 e2e
- [ ] **M3: Re-ranking & Evaluation** (~7주차) — BGE Reranker, RAGAS 평가, 권한 누수 테스트, Qdrant 비교
- [ ] **M4: Production Readiness** (~10주차) — AWS 배포, GitHub Actions CI/CD, 트레이싱
- [ ] **M5: Polish & Launch** (~12주차) — README 리라이트, 데모 영상, 아키텍처 문서

## Blog Series

진행 과정과 의사결정 기록을 블로그에 공개합니다 — [parkjongmin-ddam.github.io](https://parkjongmin-ddam.github.io)

- [ ] 1편: 왜 권한 기반 RAG인가 — IAM 엔지니어가 본 RAG의 권한 공백 *(M1 완료 시점)*
- [ ] 2편: MVP 회고 — post-filter vs pre-filter, 무엇이 더 안전한가 *(M2 완료 시점)*
- [ ] 3~4편: Re-ranking 실험 + RAGAS 평가 결과 *(M3 완료 시점)*
- [ ] 5편: AWS 배포 및 운영 회고 *(M4 완료 시점)*
- [ ] 6편: 12주 회고 + 비용 분석 *(M5 완료 시점)*

## Setup

> M2 마일스톤 완료 후 작성 예정.

## License

[MIT](LICENSE)
