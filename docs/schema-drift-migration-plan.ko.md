# Schema Migration: 민감도 기반 RBAC

**상태**: 실행 준비 완료 (M4.0)
**발견 시점**: 2026-05-20, M3.3 RAGAS 평가
**계획 보완**: 2026-05-20 (단계별 커밋 순서, eval 성공/중단 기준, disclosure_level 보정, hardening 항목을 M4.0.5로 분리)
**담당**: parkjongmin-ddam

## 배경

M3.3 평가 단계에서 평가 하네스가 접근 제어 시스템의 두 layer 사이 **schema drift**를 자동으로 발견했습니다.

- **매트릭스 layer** (`src/permission_aware_rag/permission/rules.py:ROLE_DEFAULTS`): **민감도 기반** sub_type 어휘로 설계됨 — `.handbook`, `.public`, `.documentation`, `.internal`, `.training`, `.audit`, `.forecast`. 이 명명은 *문서의 노출 수준*을 기술하기 위한 것이었음.

- **데이터 layer** (`data/documents.yaml`): **주제 기반** sub_type 어휘로 인스턴스화됨 — `.policy`, `.compensation`, `.recruitment`, `.architecture`, `.api`, `.budget`, `.campaign`, `.brand`, `.research`, `.regulatory`, `.opinion`, `.litigation`. 이 명명은 *문서의 내용 도메인*을 기술함.

순효과:
- 매트릭스 9개 정도의 엔트리가 데이터에 존재하지 않는 sub_type 참조 (dead entries)
- 데이터의 13개 정도의 sub_type이 어떤 role에도 할당되지 않음 (ABAC 룰이 작동하지 않으면 기본 거부)
- 직관적으로 접근 가능해야 할 케이스(예: 엔지니어가 `tech.architecture` 조회)에서 `Truth=0` 비율이 높게 나타나는 형태로 평가에 노출됨

이는 IAM의 전형적인 안티패턴 — *정책 어휘 드리프트* — 접근 정책과 그것이 통제하는 데이터가 서로 다른 시점에, 서로 다른 추상화로 설계된 경우 발생.

## 결정

**M3 (완료)**: 매트릭스를 직접 수정하지 않았음.

근거:
- 드리프트는 실재하며 평가가 이를 정확히 노출시킴. 즉석 매핑(`marketing.public → marketing.research`)으로 패치하면 드리프트를 숨길 뿐 본질적 긴장을 해결하지 못함.
- 수정은 데이터 영향이 있는 비자명한 스키마 변경. M3 범위 외.
- 발견 자체가 *자기 검증 가능한 시스템*을 보여주는 portfolio 자료.

**M4.0 (본 마이그레이션)**: 문서에 `sensitivity` 필드를 추가 (sub_type과 직교). RBAC 매트릭스를 `role → 허용 민감도 집합` 형태로 재작성. 원래 설계 의도를 올바른 방식으로 표현.

## 목표 스키마

`sensitivity`는 개념적으로 `sub_type`과 직교임. 현재 45개 문서 데이터셋에서는 매핑이 결정적임 (모든 `hr.policy`는 `public`, 모든 `legal.litigation`은 `privileged`). 두 필드를 분리해서 유지하는 이유는 향후 같은 sub_type 내에서 민감도가 갈리는 케이스를 위한 것 — 예: 평소엔 `internal`인 `tech.architecture` 문서가 미공개 인수합병 관련 설계를 다루는 경우 `restricted`로 격상 가능.

### 문서 추가 사항

`data/documents.yaml`의 각 문서에 추가:

```yaml
sensitivity: public | internal | restricted | privileged
```

정의:
- **public** — 모든 직원과 외주 인력이 읽을 수 있음. 제한할 비즈니스 사유 없음 (예: 모두가 준수해야 하는 정책, 브랜드 가이드라인).
- **internal** — 직원에게만 공개. 대부분 운영/작업 산출 문서의 기본값.
- **restricted** — 특정 role에 한정. 개인 데이터, 재무 상세, 보안 운영의 기본값.
- **privileged** — restricted보다 더 좁음 (예: 변호사-의뢰인 통신, 임원 전용 전략 문서).

### 현재 문서의 권장 매핑

| Sub_type | 민감도 | 사유 |
|---|---|---|
| `hr.policy` | public | 모든 직원의 필수 숙지 사항 |
| `hr.compensation` | restricted | 보상 데이터는 알 필요 원칙 |
| `hr.personnel` | restricted | 개인정보 — 프라이버시 |
| `hr.recruitment` | internal | 채용팀 + HR |
| `security.policy` | public | 전 직원 의무 인지 |
| `security.incident` | restricted | `incident_rule`이 처리 |
| `security.threat_intel` | restricted | 보안 운영 전용 |
| `security.compliance` | restricted | 감사 + 보안 도메인 |
| `tech.runbook` | internal | 엔지니어링 운영 |
| `tech.architecture` | internal | 엔지니어링 + 시니어 |
| `tech.api` | internal | 엔지니어링 계약 문서 |
| `tech.project` | restricted | `project_rule`이 처리 |
| `finance.budget` | restricted | 재무 + 임원 |
| `finance.statement` | restricted | 임원 + 감사 |
| `finance.expense` | restricted | `self_access` + `audit_rule`이 처리 |
| `finance.tax` | privileged | 임원 + 감사 전용 |
| `marketing.campaign` | internal | 마케팅 운영 |
| `marketing.brand` | public | 전 직원 브랜드 준수 |
| `marketing.research` | internal | 시장 정보 |
| `legal.contract` | restricted | `parties_rule`이 처리 |
| `legal.regulatory` | internal | 관련 role 모두의 컴플라이언스 레퍼런스 |
| `legal.opinion` | restricted | 법률 자문 |
| `legal.litigation` | privileged | 변호사-의뢰인 특권 기본값 — Step 1에서 `disclosure_level: privileged` 마커도 함께 추가 필요 |

### 매트릭스 재작성

```python
ROLE_DEFAULTS: dict[str, frozenset[str]] = {
    "employee":         frozenset({"public"}),
    "team_lead":        frozenset({"public", "internal"}),
    "executive":        frozenset({"public", "internal", "restricted"}),
    "security_officer": frozenset({"public", "internal", "restricted"}),
    "hr_specialist":    frozenset({"public", "internal", "restricted"}),
    "contractor":       frozenset({"public"}),
    "auditor":          frozenset(),  # audit_rule만 사용
}
```

### 신규 룰

`rbac_default`를 `sensitivity_rule`로 교체:

```python
def sensitivity_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """문서 민감도 수준에 따른 role 기반 접근.

    레거시 sub_type-keyed ROLE_DEFAULTS 매트릭스를 대체. 각 role은 기본
    접근 가능한 최대 민감도를 선언하며, 보다 특화된 접근은 여전히 상위
    ABAC 룰을 통해 처리됨.
    """
    sensitivity = document.get("sensitivity")
    if sensitivity is None:
        return None  # 민감도 필드 없는 문서는 기본 접근 권한 없음

    allowed = ROLE_DEFAULTS.get(principal.role, frozenset())
    if sensitivity in allowed:
        return PolicyDecision.allow(
            rule_name="sensitivity",
            reason=(
                f"role {principal.role}이 {sensitivity} 수준 문서를 읽음 "
                f"(sub_type={document.get('sub_type')})"
            ),
        )
    return None
```

## 마이그레이션 단계

**순서 원칙**: 코드는 비활성 상태로 먼저 들어가고, 데이터가 두 번째로 들어가며, 스위치는 마지막에 켜짐. 이렇게 해야 *데이터는 새 어휘를 쓰지만 룰은 옛 어휘를 참조하는* 반쪽짜리 마이그레이션 상태가 외부에 관측되지 않음.

1. **`sensitivity_rule` 코드 추가 (비활성)** (~10분)
   - `permission/rules.py`에 위 사양대로 `sensitivity_rule` 함수 추가.
   - 새 sensitivity-keyed `ROLE_DEFAULTS` 매트릭스를 기존 매트릭스 옆에 함께 추가 (마이그레이션 기간 동안 기존 것은 `LEGACY_ROLE_DEFAULTS`로 rename).
   - **`permission/policy.py:RULES`는 아직 수정하지 않음** — 새 룰은 존재하지만 연결되지 않음. 시스템 동작은 마이그레이션 전과 동일.
   - 커밋: `feat(rules): add sensitivity_rule (dormant, not yet wired)`

2. **데이터에 sensitivity 추가** (~15분)
   - `data/documents.yaml`: 45개 문서 각각에 매핑 표대로 `sensitivity:` 필드 추가.
   - DOC-044와 DOC-045 (두 개의 `legal.litigation` 문서)에는 `disclosure_level: privileged`도 함께 추가. M3에서 발견된 audit_rule 설계 갭 — 룰은 이 마커를 체크하는데 데이터에 없었음.
   - 커밋: `data: add sensitivity field + privileged disclosure markers`

3. **DB 스키마 업데이트 및 재인제스트** (~10분)
```sql
ALTER TABLE documents ADD COLUMN sensitivity TEXT;
```
   재인제스트로 백필: `uv run python scripts/ingest.py`
   - 검증: `SELECT sub_type, sensitivity, COUNT(*) FROM documents GROUP BY 1,2 ORDER BY 1;`
   - 45개 row 모두 sensitivity가 non-null이어야 함.
   - 커밋: `db: add sensitivity column (re-ingest backfill)`

4. **사전 점검: eval 영향 예측** (~10분)
   스위치 켜기 전, 예상되는 eval delta를 스크래치 노트에 적어둠:
   - TC-013, TC-014, TC-016, TC-017 (현재 Truth=0 케이스): 각각이 마이그레이션 후 non-empty Truth를 갖게 될지 예측. 케이스별 근거.
   - TC-005 sec_001 × DOC-013 (현재 recall 손실 케이스): 새 매트릭스에서 이 케이스가 유지되는지 변하는지 예측.
   - TC-009 × aud_001 × DOC-044 (privileged litigation): `disclosure_level: privileged`가 추가되었으므로 audit_rule이 명시적 DENY 해야 함. eval이 이를 반영하리라 예측.
   - 이 예측 작업은 변경이 적용되기 전에 *내가 변경을 이해하고 있다*는 자기 검증. 코드 수정은 없음.

5. **스위치 켜기** (~5분)
   - `permission/policy.py:RULES`: `rbac_default`를 `sensitivity_rule`로 교체.
   - `LEGACY_ROLE_DEFAULTS` 삭제 (더 이상 참조되지 않음).
   - 커밋: `feat(policy): switch rbac_default → sensitivity_rule`

6. **평가로 검증** (~10분)
   - `uv run python scripts/eval_retrieval.py`
   - M3.3 baseline과 Step 4 예측 모두와 비교.
   - **성공 기준**:
     - Truth=0 케이스: 4개 → 2개 이하 (TC-013, 014, 016, 017이 대부분 해결됨)
     - F1: M3.3 baseline (0.560) 유지 또는 개선
     - Eligible cases: 52개 중 28 → 32 이상으로 증가
   - **중단 기준**:
     - F1이 0.50 미만으로 하락 → 마이그레이션이 시스템을 악화시키는 중. 중단 후 매핑 표 재검토.
     - Step 4 예측과 실제 결과가 예상 외의 방식으로 어긋남 → 진행 전 조사 필요.
   - 커밋 메시지에 마이그레이션 전후 eval 결과 모두 기록.

7. **필요 시 테스트 데이터셋 갱신** (~10분)
   - 옛 매트릭스 동작에 의존하던 Truth set이 있다면 재라벨링.
   - 대부분 케이스는 변경 불필요 — Truth가 live policy의 `can_read()`로 계산되기 때문.
   - 변경이 있을 경우 커밋: `eval: relabel cases affected by sensitivity migration`

**총 추정 작업 시간**: ~70분 엔지니어링 + ~20분 리뷰.

## 리스크

- **민감도 할당은 정책 결정** — 각 문서를 민감도 tier로 분류하는 것은 기계적인 작업이 아닌 판단. 일부는 명확함 (DOC-006 hr.personnel = restricted), 일부는 모호함 (marketing.research는 internal일 수도 restricted일 수도). 대량 업데이트 전 정책 승인 필요.

- **평가 baseline 변화** — 마이그레이션 후 F1 수치 변경됨. 블로그 narrative 일관성을 위해 마이그레이션 전후 baseline을 모두 기록.

- **하위 호환성** — `sensitivity` 필드 없는 문서는 `sensitivity_rule`에서 `None`을 받아 기본 거부로 폴스루. 마이그레이션은 45개 문서 전체에 대해 원자적으로 수행되어야 함.

## 롤백

`permission/policy.py:RULES`를 `rbac_default` 포함으로 되돌림. 문서의 sensitivity 컬럼은 사용되지 않으면 무해. 총 롤백 시간: ~5분.

## 범위 외

- 필드 단위 민감도 (예: 문서 내 특정 필드만 마스킹).
- 시간 제한 민감도 (예: 엠바고 후 public이 되는 문서).
- 사용자 주도 민감도 태깅 (사용자가 본인 문서 표시).
- 부모 문서로부터의 민감도 상속.

이들은 미래의 유효한 고려사항이지만 더 깊은 스키마 작업이 필요하며 본 마이그레이션의 범위 외입니다.

### 별도 트랙으로 관리되는 인접 작업

M3 시점에 누적된 두 가지 hardening 항목은 commit 이력을 깨끗하게 유지하기 위해 본 마이그레이션에 의도적으로 포함하지 않음:

- **JWT_SECRET_KEY 길이** — 현재 23바이트로 `InsecureKeyLengthWarning` 발생. 32바이트 이상 random 값으로 교체. M4.0.5 (배포 전 hardening)로 분류, M4.1 배포 작업 중 Secrets Manager를 통해 처리. 본 마이그레이션에서는 작업하지 않음.
- **Pydantic `extra="forbid"` strict mode** — silent kwarg drop (예: `reranker_score` vs `rerank_score`)으로 M3에서 실제 디버깅 시간을 소모. 모든 Pydantic 모델에 `model_config = ConfigDict(extra="forbid")` 추가. M4.0.5로 분류, 스키마 마이그레이션과 별도 커밋으로 처리.

## 참조

- 최초 드리프트 발견: M3.3 eval 실행, 2026-05-20
- 평가 하네스: `scripts/eval_retrieval.py`
- 테스트 데이터셋: `eval/dataset.yaml` (18 cases × 52 persona-case pairs)
- 영향받는 코드: `src/permission_aware_rag/permission/rules.py`
- 영향받는 데이터: `data/documents.yaml`