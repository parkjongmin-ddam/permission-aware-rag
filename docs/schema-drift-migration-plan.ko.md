# Schema Migration: 민감도 기반 RBAC

**상태**: M4+ 단계로 연기
**발견 시점**: 2026-05-20, M3.3 RAGAS 평가
**담당**: 미정

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

**M3 (현재 마일스톤)**: 매트릭스를 직접 수정하지 않음.

근거:
- 드리프트는 실재하며 평가가 이를 정확히 노출시킴. 즉석 매핑(`marketing.public → marketing.research`)으로 패치하면 드리프트를 숨길 뿐 본질적 긴장을 해결하지 못함.
- 수정은 데이터 영향이 있는 비자명한 스키마 변경. M3 범위 외.
- 발견 자체가 *자기 검증 가능한 시스템*을 보여주는 portfolio 자료.

**M4+ (실제 운영 경로)**: 문서에 `sensitivity` 필드를 추가 (sub_type과 직교). RBAC 매트릭스를 `role → 허용 민감도 집합` 형태로 재작성. 원래 설계 의도를 올바른 방식으로 표현.

## 목표 스키마

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
| `legal.litigation` | privileged | 변호사-의뢰인 특권 기본값 |

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

1. **데이터에 민감도 추가** (~15분)
   `data/documents.yaml`: 45개 문서 각각에 위 매핑 표대로 `sensitivity:` 필드 추가.

2. **DB 스키마 업데이트** (~10분)
```sql
   ALTER TABLE documents ADD COLUMN sensitivity TEXT;
```
   재인제스트로 백필: `uv run python scripts/ingest.py`

3. **`rbac_default`를 `sensitivity_rule`로 교체** (~15분)
   - `permission/rules.py`에 `sensitivity_rule` 추가
   - `permission/policy.py:RULES` 리스트를 신규 룰 사용하도록 수정
   - `ROLE_DEFAULTS`를 민감도 키 frozenset으로 변경
   - 더 이상 사용하지 않는 sub_type 엔트리 삭제

4. **평가로 검증** (~10분)
   - `uv run python scripts/eval_retrieval.py`
   - M3.3 baseline과 비교: F1 0.464 → 0.560
   - 기대 결과: `Truth=0` 케이스 감소, F1 유지 또는 개선

5. **필요 시 테스트 데이터셋 갱신** (~10분)
   - 옛 매트릭스 동작에 의존하던 Truth set이 있었다면 재라벨링

**총 추정 작업 시간**: ~60분 엔지니어링 + ~30분 리뷰.

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

## 참조

- 최초 드리프트 발견: M3.3 eval 실행, 2026-05-20
- 평가 하네스: `scripts/eval_retrieval.py`
- 테스트 데이터셋: `eval/dataset.yaml` (18 cases × 52 persona-case pairs)
- 영향받는 코드: `src/permission_aware_rag/permission/rules.py`
- 영향받는 데이터: `data/documents.yaml`