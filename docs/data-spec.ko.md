# BWCorp 권한 인식 RAG: 데이터 명세서

> 🇺🇸 English version: [data-spec.md](./data-spec.md)

본 문서는 이 프로젝트에서 구현하는 권한 인식(permission-aware) RAG 시스템의 시나리오,
페르소나, 문서 카테고리, 권한 매트릭스를 정의한다.

여기 등장하는 데이터는 모두 가상이다. 페르소나와 권한 패턴은 저자가 실제 운영
환경에서 다뤄온 IAM 패턴(국내 대기업에서 5년 이상 ADFS, SAML, OIDC, AD 기반
인가 시스템 운영 경험)을 바탕으로 설계했다.

## 1. 시나리오 개요

**BWCorp**은 약 500명 규모의 한국 중견 IT 솔루션 기업으로 가정한다. 조직은
다음과 같은 차원을 가진다.

- **부서**: HR, Security, Tech (Engineering + Infrastructure), Finance, Marketing, Legal
- **조직 계층**: Employee → Team Lead → Director → VP → C-level
- **횡단적 역할**: Security Officer, Auditor는 부서를 가로질러 동작함
- **외부 인력**: Contractor는 프로젝트 단위·기간 단위로 제한된 접근권을 가짐

이 시나리오는 단순 RBAC(역할 기반 접근 제어)만으로는 깔끔하게 모델링할 수
없는 권한 패턴을 의도적으로 노출하도록 설계되어 있다. 그 결과 RAG 검색 계층
에 ReBAC(관계 기반)와 ABAC(속성 기반) 확장이 필요하게 된다.

## 2. 페르소나

각기 다른 권한 패턴을 demonstrate하기 위해 페르소나 7종을 정의한다. 각 페르소나는
**역할**(문자열 식별자) + **속성**(key-value 쌍 묶음)의 조합이며, 인증 노드가 발급하는
mock JWT 토큰의 클레임으로 인코딩된다.

### 2.1 페르소나 요약

| Role | 패턴 | Clearance | Access Mode | 범위 |
|---|---|---|---|---|
| `employee` | RBAC 베이스라인 | 1 | R | 본인 부서 + 자기 접근 |
| `team_lead` | 계층적 RBAC | 2 | R/W | 본인 팀 + 본인 부서 |
| `executive` | 최상위 계층 | 4 | R/W | 본인 디비전 전체 |
| `security_officer` | 횡단적 (ReBAC) | 3 | R/W | 전 부서 (security scope) |
| `contractor` | 외부 (ABAC) | 0 | R | 프로젝트 한정, 기간 한정 |
| `auditor` | 읽기 전용 감사 | 3 | R only | 감사 범위 (의무 로깅) |
| `hr_specialist` | 부서 전문가 | 2 (HR) / 1 (그 외) | R/W (HR) / R (그 외) | HR 도메인 |

### 2.2 employee — RBAC 베이스라인

일반 인증 사용자. 본인이 속한 부서의 문서와 HR 내 *"본인 관련"* 문서(본인 인사평가,
급여명세 등)에 대해 읽기 권한을 가진다.

```yaml
role: employee
attributes:
  department: tech            # hr, security, tech, finance, marketing, legal 중 하나
  clearance_level: 1
  team_name: backend
  location: kr
  user_id: user_emp_001
```

**권한 패턴**: 부서 기반 스코프를 가진 표준 RBAC.

### 2.3 team_lead — 계층적 RBAC

부서 내 특정 팀의 관리자. 팀 내부 문서(팀 기획, 직속 부하 인사평가 등) + 동일
부서의 employee가 볼 수 있는 모든 문서에 접근 가능하다.

```yaml
role: team_lead
attributes:
  department: tech
  team_name: backend
  clearance_level: 2
  direct_reports: [user_emp_001, user_emp_002, user_emp_003]
  location: kr
  user_id: user_tl_001
```

**권한 패턴**: RBAC + 계층 (direct_reports 관계를 통한 self-access 확장).

### 2.4 executive — 최상위 계층

임원급(Director / VP / C-level). 디비전 전체의 전략 문서에 대한 가시성을 가진다.
다만 보안 관련 운영 문서는 **자동으로 보이지 않음** — 이는 security_officer 범위로
별도 관리되며 조직 계층을 따라 흐르지 않는다(의도된 ReBAC 패턴).

```yaml
role: executive
attributes:
  division: tech              # tech, business, corporate
  clearance_level: 4
  executive_level: vp         # director, vp, cxo
  location: kr
  user_id: user_exec_001
```

**권한 패턴**: 높은 clearance를 가진 RBAC. 다만 superuser는 아님. 예를 들어, Business
디비전 임원은 Tech 디비전의 내부 아키텍처 문서를 볼 수 없다.

### 2.5 security_officer — 횡단적 (ReBAC)

보안/InfoSec 담당자. 문서의 발생 부서와 무관하게 보안 관련 문서에 대해 부서 횡단
접근권을 가진다. 핵심 패턴: 주니어 security_officer가 임원보다 security_incident에
대한 권한이 **더 높을 수 있음** — 접근권이 조직 계층이 아닌 **보안 도메인과의 관계**
로 결정되기 때문이다.

```yaml
role: security_officer
attributes:
  clearance_level: 3
  scope: ["all_departments"]
  specialization: incident_response   # incident_response, audit, policy, threat_intel
  location: kr
  user_id: user_sec_001
```

**권한 패턴**: ReBAC. *"clearance 높은 employee"*로 깔끔하게 모델링되지 않음 —
접근권은 보안 기능과의 관계가 부여한다.

### 2.6 contractor — 외부 (ABAC)

외부 인력(예: 컨설팅 회사 직원). 특정 프로젝트, 특정 기간 동안만 제한적 접근권을
부여받음. 접근권은 오로지 속성에 의해 정의되며, 조직 계층과 무관하다.

```yaml
role: contractor
attributes:
  company: ExternalCo
  project_scope: [project_alpha, project_beta]
  start_date: "2026-06-01"
  end_date: "2026-09-30"
  clearance_level: 0
  allowed_categories: [tech]          # 부서가 아닌 명시적 allow-list
  user_id: user_ext_001
```

**권한 패턴**: 순수 ABAC. 검색 노드는 다음 조건을 모두 평가해야 한다 —
`(현재 시각 in [start_date, end_date]) AND (doc.project in project_scope)
AND (doc.category in allowed_categories)`.

### 2.7 auditor — 읽기 전용 감사

내부 또는 외부 감사 인력(예: 컴플라이언스, SOX, 내부 감사). 부서를 가로질러
민감 문서에 대한 **읽기 권한**을 가지나 수정은 불가하다. 모든 접근은 의무적으로
일반 사용자보다 강화된 메타데이터와 함께 로깅된다.

```yaml
role: auditor
attributes:
  clearance_level: 3
  audit_scope: [financial, security, compliance]
  access_mode: read_only
  mandatory_audit_logging: true
  audit_engagement_id: AUDIT-2026-Q3-001
  end_date: "2026-12-31"
  user_id: user_aud_001
```

**권한 패턴**: 다차원. 권한이 *"누가(Who)"*뿐 아니라 *"어떻게(How)"* (R vs R/W) 와
*"어떻게 추적되는가(Audit logging level)"*까지 포함한다는 것을 보여준다.

### 2.8 hr_specialist — 부서 전문가 (수평)

HR 도메인 내에서 격상된 접근권을 가진 HR 전문가(예: Compensation Analyst, Recruiter,
HR Policy Author). team_lead와 다른 점: 격상이 **수직적(팀 내)** 이 아니라
**수평적(부서 내)** 이다.

```yaml
role: hr_specialist
attributes:
  department: hr
  specialization: compensation    # compensation, recruitment, policy, benefits
  clearance_level: 2              # HR 내에서 2; HR 외에서 1
  cross_team_access: true         # HR 내에서만
  location: kr
  user_id: user_hrs_001
```

**권한 패턴**: Role × Category 매트릭스가 균질하지 않음을 보여준다 — hr_specialist가
HR 문서에 접근할 때와 다른 부서 문서에 접근할 때 적용되는 규칙이 매우 다르다.

### 2.9 패턴 커버리지 요약

| 권한 패턴 | 이를 시연하는 페르소나 |
|---|---|
| 표준 RBAC | employee |
| 계층적 RBAC | team_lead, executive |
| 횡단적 ReBAC | security_officer |
| 의무 로깅이 있는 읽기 전용 | auditor |
| 부서 한정 전문화 | hr_specialist |
| 속성 기반 + 기간 한정 + 프로젝트 스코프 | contractor |
| 자기 접근 예외 (본인 데이터 카브아웃) | 전 역할 (HR self-docs) |

이 조합은 **순수 RBAC, 순수 ReBAC, 순수 ABAC 어느 단일 모델로도 모든 접근 요구
사항을 만족할 수 없도록** 의도적으로 설계되었다. 검색 계층은 여러 차원의 검사를
조합해야 한다.

## 3. 문서 카테고리

회사의 문서 영역을 최상위 카테고리 6개로 정리한다. 각 문서는 정확히 하나의
primary category, 선택적 sub-type, 그리고 권한 필터링에 사용되는 추가 속성
(project_id, case_id, subject 등)을 태그로 가진다.

### 3.1 카테고리 요약

| 카테고리 | 민감도 (typical) | 특수 패턴 |
|---|---|---|
| `hr` | Medium (혼합) | 본인 기록에 대한 self-access 카브아웃 |
| `security` | High | security_officer를 통한 횡단 접근 |
| `tech` | Low–Medium | 자주 프로젝트 단위로 스코프됨 |
| `finance` | High | Auditor 주 무대, 강화 로깅 |
| `marketing` | Low | 폭넓게 접근 가능한 베이스라인 |
| `legal` | Critical | Case 기반 ABAC (이름이 명시된 당사자) |

### 3.2 `hr` — Human Resources

HR 정책, 인사평가, 복리후생, 채용.

**Sub-types**:
- `hr.policy` — 회사 전체 HR 정책 (사원 핸드북, 휴가 정책)
- `hr.compensation` — 급여 밴드, 보너스 체계
- `hr.personnel` — 개별 직원 기록 (인사평가, 급여명세)
- `hr.recruitment` — 채용 파이프라인, 후보자 평가

**특수 패턴 — Self-access 카브아웃**: 인증된 사용자는 `doc.subject == user.user_id`
인 `hr.personnel` 문서를 다른 제한과 무관하게 항상 읽을 수 있다. 직원이 자신의
HR 기록을 항상 볼 수 있어야 한다는 현실을 모델링한다.

### 3.3 `security` — Security & InfoSec

보안 정책, 사고 보고서, 위협 인텔리전스, 감사 결과.

**Sub-types**:
- `security.policy` — 허용 가능한 사용 정책, 비밀번호 정책
- `security.incident` — 사고 보고서, RCA 문서
- `security.threat_intel` — 위협 환경 브리핑
- `security.compliance` — SOC2 / ISO27001 문서

**특수 패턴 — 횡단 접근**: 주니어 `security_officer`가 시니어 `executive`보다
`security.incident` 문서에 대해 **더 많은 접근권**을 가질 수 있다. 접근권이 계층
clearance가 아닌 보안 기능과의 관계에 의해 부여되기 때문이다. 이것이 본 프로젝트의
핵심 ReBAC 패턴이다.

### 3.4 `tech` — Technology & Engineering

아키텍처 문서, API 명세, 운영 런북, 프로젝트 문서.

**Sub-types**:
- `tech.architecture` — 시스템 아키텍처, 설계 문서
- `tech.api` — API 명세, 통합 가이드
- `tech.runbook` — 운영 런북
- `tech.project` — 프로젝트별 문서 (항상 `project_id` 태그 보유)

**특수 패턴 — 프로젝트 스코프**: `tech.project` 문서는 `project_id` 속성을 가진다.
Contractor는 본인의 `project_scope`에 해당 ID가 포함된 경우에만 접근할 수 있다.
부서 간 협업하는 Tech 인력도 이 경로를 통한다.

### 3.5 `finance` — Finance & Accounting

예산, 재무제표, 경비 보고서, 세무 기록.

**Sub-types**:
- `finance.budget` — 연간 / 분기 예산 문서
- `finance.statement` — 재무제표 (P&L, 대차대조표)
- `finance.expense` — 경비 보고서, T&E 기록 (개인별)
- `finance.tax` — 세무 신고, 감사 관련 기록

**특수 패턴 — Auditor 주 무대 + 강화 로깅**: auditor 페르소나의 일차 접근 대상.
모든 접근(읽기)은 확장 메타데이터(audit_engagement_id, IP, timestamp, 조회된 문서 ID)
와 함께 로깅된다. `finance.expense`는 `hr.personnel`과 유사한 self-access 카브아웃을
적용받는다.

### 3.6 `marketing` — Marketing & Brand

캠페인, 브랜드 가이드라인, 시장 조사.

**Sub-types**:
- `marketing.campaign` — 캠페인 기획, 자료
- `marketing.brand` — 브랜드 가이드라인, 로고
- `marketing.research` — 시장 조사 보고서

**특수 패턴 — 폭넓게 접근 가능한 베이스라인**: 가장 민감도가 낮은 카테고리.
`marketing.brand` 문서 대부분은 contractor를 포함한 모든 인증 사용자가 읽을 수 있다.
다른 제한적인 카테고리와 대비하는 기준선이 된다.

### 3.7 `legal` — Legal & Compliance

계약서, 규제 신고, 법무 의견서, 소송 관련.

**Sub-types**:
- `legal.contract` — 상업 계약서, NDA
- `legal.regulatory` — 규제 신고, 컴플라이언스 보고서
- `legal.opinion` — 법무 자문 메모
- `legal.litigation` — 소송 관련 문서

**특수 패턴 — Case 기반 ABAC**: 다수의 `legal` 문서는 `case_id`와 `parties` 리스트를
가진다. 접근권은 Legal팀 소속이거나 `parties`에 명시적으로 이름이 등재된 경우에만
부여된다. 이 패턴은 역할만으로는 모델링할 수 없으며, 문서별 속성에 의존한다
(문서 자체가 누가 볼 수 있는지 명시).

### 3.8 카테고리 × Sub-type 민감도 맵

이 표는 섹션 4의 권한 매트릭스 입력값을 미리 보여준다. *민감도*는 일반적인 기밀성
수준을, *기본 reader pool*은 추가 속성 검사 없이 읽을 수 있는 기본 페르소나 집합을
의미한다.

| 카테고리 | Sub-type | 민감도 | 기본 Reader Pool |
|---|---|---|---|
| `hr` | `policy` | Low | 모든 employee+ |
| `hr` | `compensation` | High | hr_specialist, executive |
| `hr` | `personnel` | Critical | Self + hr_specialist + auditor |
| `hr` | `recruitment` | Medium | hr_specialist + 채용 중인 team_lead |
| `security` | `policy` | Low | 모든 employee+ |
| `security` | `incident` | Critical | security_officer + 명시된 stakeholders |
| `security` | `threat_intel` | High | security_officer |
| `security` | `compliance` | High | security_officer + auditor |
| `tech` | `architecture` | Medium | Tech 부서 + 프로젝트 멤버 |
| `tech` | `api` | Low | 모든 employee+ |
| `tech` | `runbook` | Medium | Tech 부서 |
| `tech` | `project` | Variable | 프로젝트 멤버 (모든 역할) |
| `finance` | `budget` | High | Finance + executive + auditor |
| `finance` | `statement` | Critical | Finance + executive + auditor |
| `finance` | `expense` | Medium | Self + finance + auditor |
| `finance` | `tax` | Critical | Finance + auditor |
| `marketing` | `campaign` | Low | 모든 employee+ |
| `marketing` | `brand` | Low | 모든 employee+ contractor (제한적) |
| `marketing` | `research` | Medium | Marketing + executive |
| `legal` | `contract` | High | Legal + 명시된 당사자 |
| `legal` | `regulatory` | High | Legal + executive + auditor |
| `legal` | `opinion` | Critical | Legal + 명시된 당사자 |
| `legal` | `litigation` | Critical | Legal + 명시된 당사자 + executive (제한적) |

### 3.9 패턴 커버리지 요약

| 권한 패턴 | 이를 demonstrate하는 카테고리 |
|---|---|
| Self-access 예외 | `hr.personnel`, `finance.expense` |
| 횡단 오버라이드 (ReBAC) | `security.incident`, `security.compliance` |
| 프로젝트 스코프 (ABAC) | `tech.project` |
| 강화 감사 로깅 | 모든 `finance.*`, `security.compliance` |
| Case 기반 당사자 등재 (ABAC) | `legal.contract`, `legal.opinion`, `legal.litigation` |
| 폭넓은 베이스라인 (제한 낮음) | `marketing.brand`, `marketing.campaign` |

카테고리는 **섹션 2의 각 주요 권한 패턴이 적어도 하나의 구체적인 문서 카테고리에
대응되도록** 설계되었다. 이러한 페어링이 섹션 4의 매트릭스를 단순한
*"role.clearance ≥ doc.clearance"* 체크로 환원할 수 없게 만든다.

## 4. 권한 매트릭스

### 4.1 접근 표기법

| 기호 | 의미 |
|---|---|
| `R` | 읽기 권한 |
| `R/W` | 읽기와 쓰기 |
| `-` | 접근 없음 (default deny) |
| `S` | Self-access only (`doc.subject == user.user_id`) |
| `P` | 프로젝트 스코프 (`doc.project_id ∈ user.project_scope`) |
| `M` | Member-only (`user.user_id ∈ doc.parties`) |
| `C` | 조건부 — 섹션 4.3의 sub-type 세부 규정 참조 |

`auditor`의 모든 접근은 의무 감사 로깅이 적용된다 (섹션 4.4의 Rule 5).

### 4.2 기본 접근 매트릭스 (Role × Category)

카테고리 수준의 베이스라인이다. Sub-type별 오버라이드는 섹션 4.3에 있다. 섹션 4.4의
조건부 규칙은 이 표가 보여주지 않는 추가 접근을 부여할 수 있다.

| Role | `hr` | `security` | `tech` | `finance` | `marketing` | `legal` |
|---|---|---|---|---|---|---|
| **employee** | C | R(policy) | R(own dept) + P | S(expense) | R | M |
| **team_lead** | C | R(policy) | R/W(own team) + P | S(expense) | R | M |
| **executive** | C | R(policy) | R(own division) | R(budget, statement) | R/W | R(regulatory) |
| **security_officer** | - | R/W | R(security-tagged) | R(compliance) | - | M(security-related) |
| **contractor** | - | - | P (read-only) | - | R(brand only) | - |
| **auditor** | R(personnel) | R(compliance) | - | R(all, logged) | - | R(regulatory) |
| **hr_specialist** | R/W | R(policy) | R(own dept) | - | R | - |

### 4.3 Sub-type 세부 규정

Sub-type의 접근권이 섹션 4.2의 카테고리 기본값과 다른 경우 여기에 명시한다.
sub-type이 여기에 없으면 4.2를 상속받는다.

#### 4.3.1 `hr.compensation`
| Role | 접근 |
|---|---|
| employee, team_lead, contractor | `-` |
| executive | `R` |
| hr_specialist | `R/W` |
| auditor | `R` (로깅) |

#### 4.3.2 `hr.personnel`
| Role | 접근 |
|---|---|
| 전 역할 | `S` (오로지 `doc.subject == user.user_id`) |
| hr_specialist | `R/W` (모든 personnel 문서) |
| auditor | `R` (로깅) |

#### 4.3.3 `hr.recruitment`
| Role | 접근 |
|---|---|
| employee, contractor | `-` |
| team_lead | `R/W` — `user.attributes.is_hiring == true`인 경우에만 |
| hr_specialist | `R/W` |
| executive | `R` |

#### 4.3.4 `security.incident`
| Role | 접근 |
|---|---|
| 기본 전 역할 | `-` |
| security_officer | `R/W` |
| 명시된 stakeholder | `R` (`user.user_id ∈ doc.stakeholders`인 경우) |
| executive | `R` — `doc.severity ∈ [critical]` AND `doc.executive_briefed == true`인 경우에만 |

#### 4.3.5 `security.threat_intel`
| Role | 접근 |
|---|---|
| security_officer | `R` |
| 그 외 전 역할 | `-` |

#### 4.3.6 `security.compliance`
| Role | 접근 |
|---|---|
| security_officer | `R/W` |
| auditor | `R` (로깅) |
| 그 외 전 역할 | `-` |

#### 4.3.7 `tech.project`
조직 계층이 아닌 프로젝트 멤버십을 통한 접근. 섹션 4.4의 조건부 Rule 2 참조.

#### 4.3.8 `finance.statement`, `finance.budget`, `finance.tax`
| Role | 접근 |
|---|---|
| employee, team_lead, hr_specialist | `-` |
| executive | `R` |
| auditor | `R` (로깅) |
| Finance 부서 인력 (`department == 'finance'` 속성) | `R/W` |

#### 4.3.9 `legal.litigation`
| Role | 접근 |
|---|---|
| 기본 전 역할 | `M` (반드시 `doc.parties`에 포함) |
| Legal 부서 인력 | `R/W` |
| executive | `R` — `doc.disclosure_level == 'executive_briefing'`인 경우에만 |
| auditor | `R` — `doc.case_type` ∈ `auditor.audit_scope`인 경우 (로깅) |

### 4.4 조건부 규칙

카테고리를 가로질러 적용되는 규칙들. 섹션 4.5에 정의된 순서로 평가된다.

#### Rule 1 — Self-Access 카브아웃
```
IF doc.subject == user.user_id
   AND doc.category.sub_type IN ['hr.personnel', 'finance.expense']:
    ALLOW Read
```
사용자가 자신의 기록은 항상 볼 수 있어야 한다는 법적 요구사항을 모델링한다.

#### Rule 2 — 프로젝트 멤버십
```
IF doc.project_id IS NOT NULL:
    IF user.user_id IN doc.project_members:
        ALLOW Read (역할에 따라 R/W)
    IF doc.project_id IN user.attributes.project_scope:
        ALLOW Read  # contractor의 주 접근 경로
```

#### Rule 3 — 명시된 당사자 (Case 기반)
```
IF doc.category == 'legal' AND doc.parties IS NOT NULL:
    IF user.user_id IN doc.parties:
        ALLOW Read
```

#### Rule 4 — 시간 제약
```
IF user.role == 'contractor':
    IF NOT (user.start_date <= NOW() <= user.end_date):
        DENY ALL (다른 모든 규칙을 오버라이드)
```
contractor에만 적용. 본 명세에서는 다른 역할의 권한은 시간 제약을 받지 않는다
(추후 확장 가능).

#### Rule 5 — 감사 로깅 강제
```
IF user.role == 'auditor':
    WRAP 모든 부여된 접근에 다음을 적용:
        - log(audit_engagement_id, user_id, doc_id, timestamp, retrieved_chunks)
        - tamper-evident audit_log 테이블에 저장
```

#### Rule 6 — 횡단 오버라이드 (security_officer)
```
IF user.role == 'security_officer'
   AND (doc.category == 'security' OR doc.has_tag('security')):
    ALLOW Read (역할에 따라 R/W)
# 조직 계층 기반 기본 거부를 오버라이드함.
```

### 4.5 평가 순서

검색 계층은 다음 순서로 권한 검사를 조합한다. **첫 번째로 접근을 부여하는 규칙이
승리**한다. 어떤 규칙도 접근을 부여하지 않으면 해당 문서는 결과에서 제외된다.

1. **Rule 4** (시간 제약) — 만료 시 즉시 거부
2. **Rule 6** (횡단) — security_officer 오버라이드
3. **Rule 1** (Self-Access) — 보편적 카브아웃
4. **Rule 2** (프로젝트 멤버십) — `tech.project` 문서용
5. **Rule 3** (명시된 당사자) — parties 리스트가 있는 `legal.*` 문서용
6. **기본 매트릭스 (4.2)** + sub-type 세부 규정 (4.3)
7. **Rule 5** (감사 로깅 wrap) — auditor의 모든 부여된 접근에 추가 적용

한 사용자에게 다중 역할이 적용되는 경우(표준은 아니나 가능), **부여된 권한의 합집합**
이 유효 권한이 된다.

### 4.6 설계 결정

핵심 선택과 그 근거:

- **글로벌 슈퍼유저가 없다.** C-level 임원조차 기본으로는 `security.incident`를 볼 수
  없다. 보안은 계층의 정점이 아닌 횡단적 차원이다. 이것이 검색 계층 ReBAC 패턴의
  원동력이다.

- **Self-access는 보편적이며 역할 종속이 아니다.** 모든 역할에 대해 발화하는 Rule로
  구현된다. GDPR/PIPA의 정보 주체 권리를 반영하며, naive RBAC 시스템이 가장 흔히
  잘못 모델링하는 패턴 중 하나다.

- **Contractor 접근은 가산적이다.** Contractor는 기본 접근권이 없다. 권한은 전적으로
  `allowed_categories`와 `project_scope` 속성에 의해 정의된다. 외부 인력에 대한
  가장 안전한 기본값이다.

- **Auditor의 R/W는 메타데이터에 한한다.** Auditor는 운영 문서를 수정하지 않는다.
  여기서 R/W는 감사 주석, 발견 사항, audit_log 테이블 자체를 의미한다.

- **부서 속성이 역할보다 더 결정적이다.** `role: employee` + `department: finance`인
  사용자와 `role: employee` + `department: marketing`인 사용자는 접근권이 다르다.
  매트릭스가 의도적으로 균질하지 않으며, 역할만으로는 부족함(순수 RBAC의 한계)을
  보여준다.

- **조건부 규칙은 우선순위 순서대로 평가된다.** 일부 규칙은 부여(Rule 6)하고 일부는
  거부(Rule 4)하기 때문에 4.5의 순서가 중요하다. 강한 거부(시간 만료)가 부여를
  이기도록 순서를 선택했다.

## 5. 엣지 케이스

실제 권한 시스템은 경계 상황에서 흥미롭게 깨진다. 검색 계층이 이런 상황에서도
예측 가능하고 안전하게 동작하도록, 다음 다섯 가지를 본 명세에서 의도적으로 다룬다.

### 5.1 권한 메타데이터가 없는 문서

**시나리오**: 문서가 `category`나 `sub_type` 속성 없이, 혹은 메타데이터가
손상된 채로 코퍼스에 수집된 경우.

**결정**: **기본 거부 (Default-deny).** 검색 계층은 메타데이터가 없는 문서를
역할과 무관하게 모든 사용자에게 접근 불가로 취급한다. 수집 파이프라인은
이러한 문서가 검색 가능한 저장소로 흘러 들어가지 못하게 거부하거나 격리
해야 한다.

**근거**: 메타데이터 결손 시 기본 허용은 실 시스템에서 권한 누수의 가장 흔한
원인이다. Fail-closed가 fail-open보다 안전하다.

### 5.2 다중 태그 문서 (횡단적 콘텐츠)

**시나리오**: 한 문서가 진정으로 여러 카테고리에 속하는 경우 — 예를 들어 *"HR
Security Awareness Policy"*는 HR이면서 Security이다. 혹은 *"Q4 Financial
Compliance Report"*는 Finance이면서 Legal이다.

**결정**: 각 문서는 정확히 하나의 **primary category** (`doc.category`)와, 선택적
**secondary tag** (`doc.tags: [...]`) 를 가진다. 권한 평가는 primary category로 매트릭스
조회를 수행하고, secondary tag는 Rule 6 (security_officer 오버라이드) 및 감사 스코핑에
사용한다.

**근거**: Primary category를 강제하면 매트릭스가 평가 가능해진다. Tag는 수평적 관심사
(예: security_officer는 카테고리 또는 태그에 `security`가 있는 모든 문서를 읽을 수 있음)
를 처리한다.

### 5.3 충돌 해결: 명시적 Sub-type 거부 vs Rule 부여

**시나리오**: Sub-type 4.3.5는 `security.threat_intel`이 security_officer를 제외한 모든
역할에 대해 `-`이라 명시한다. 그러나 Rule 6(횡단 오버라이드)은 security_officer에게
모든 `security.*` 문서 접근권을 부여한다. 만약 미래에 별도 규칙(예: *"임원 긴급 브리핑"*
규칙)이 임원에게 `security.threat_intel` 접근권을 부여하려 한다면?

**결정**: **Sub-type 세부 규정(4.3)의 명시적 거부가 Rule 부여(4.4)를 이긴다.** 어떤
역할에 대해 sub-type이 `-`로 표시되어 있다면, 조건부 규칙으로 오버라이드할 수 없다.
유일한 예외는 Rule 1 (Self-Access) — `hr.personnel`과 `finance.expense`에 대해
sub-type 검사 이전에 보편적으로 적용된다(섹션 4.5의 평가 순서에 따름).

**근거**: 유연성보다 예측 가능성. 새 규칙이 sub-type 거부를 오버라이드할 수 있다면
매트릭스가 감사하기 어려워진다. 새 접근권 부여는 sub-type 자체를 개정해야 한다.

### 5.4 문서 존재 여부 vs 콘텐츠 가시성

**시나리오**: 사용자가 *"What was the breach last month?"*라고 질의한다. 검색 계층은
3개의 관련 `security.incident` 문서를 찾지만, 사용자(일반 employee)는 접근권이 없다.
답변은 어떻게 해야 하나?

- (a) "I have no information about that." (완전 거부 — 문서 부존재처럼 응답)
- (b) "관련 문서가 3건 있지만 권한이 없어 볼 수 없습니다." (존재 유출)
- (c) "I cannot answer that question." (일반 거부)

**결정**: **기본 질의에 대해서는 (a), 고민감도 카테고리(security, finance, legal.litigation)
패턴 매칭 질의에 대해서는 (c).** Answer Node는 숨겨진 문서의 존재를 인정하지 않는
일반 부인 응답을 생성한다.

**근거**: (b)는 민감 문서의 존재 자체를 유출 — 그 자체가 정보 공개다. (c)는 사용자의
접근권 부족이 사이드 채널로 드러나지 않도록, 제한된 카테고리를 강하게 타겟팅하는
질의에 대해 사용한다.

**구현 노트**: 이는 Retrieval이 아닌 Answer Node에서 구현한다. Retrieval은 정확히
빈 셋을 반환하고, 차별화는 응답 생성 단계에서 일어난다.

### 5.5 질의 패턴을 통한 정보 누수

**시나리오**: 사용자가 접근할 수 없는 문서 제목과 일치하는 용어로 반복 질의한다.
콘텐츠가 반환되지 않더라도 검색 latency, 임베딩 점수, LLM 응답이 구조 정보를
누출할 수 있다.

**결정**: 본 명세의 전체 범위 밖. 다만 다음 완화 조치가 설계상 반영되어 있다.

- **검색 수준**: 권한 필터링은 DB 쿼리에서 일어남(post-filter 아님). 검색기는
  필터링된 문서를 보지조차 못하므로 timing 차이가 없다.
- **로깅 수준**: 빈 결과를 반환하는 질의를 포함한 모든 질의가 사용자 역할과 질의
  텍스트와 함께 로깅된다. 이 로그에 대한 anomaly detection은 Future Extension
  (섹션 7)이다.
- **Rate-limiting**: 저 clearance 사용자의 반복적인 고민감도 질의는 Audit Logger에
  소프트 경고를 트리거한다. M1에서 구현은 안 하지만 설계상 반영.

**근거**: RAG 시스템에 대한 사이드 채널 공격은 부상하는 연구 영역이다(예: 임베딩
역공학, 프롬프트 기반 추출). 프로덕션급 시스템은 이를 다뤄야 한다. 본 명세는
완전 해결을 주장하지 않으면서도 위협 표면을 인지한다.

### 5.6 한 사용자에 대한 다중 역할 (향후 고려)

**시나리오**: 한 사용자가 `team_lead`이면서 `security_officer`인 경우. 권한은
어떻게 조합되나?

**결정 (현 명세)**: 사용자당 단일 primary 역할. 다중 역할 지원은 **Future Extension**
(섹션 7). 구현 시 **부여된 권한의 합집합**이 적용된다(섹션 4.5 마지막 노트에 따름).

**근거**: M1/M2 구현 단순화를 위해 사용자당 단일 역할 유지. 대부분의 실 조직은
다중 역할을 *"한 토큰에 모든 역할 인코딩"*보다는 *"맥락별로 다른 JWT 발급"*
(예: *"이 작업에 대해서는 security_officer로 행세"*)으로 해결한다.

## 6. 샘플 문서

## 6. 샘플 문서

본 섹션은 섹션 3에 정의된 24개 카테고리 × sub-type 조합을 모두 커버하는 45개의
가상 문서를 카탈로그화한다. 카탈로그는 세 가지 목적을 갖는다.

1. **구체적 그라운딩** — 섹션 2~4의 추상적 패턴을 실 예로 연결
2. **테스트 fixture 소스** — M2 구현 단계에서 `data/documents.yaml`(또는 등가물)로 변환됨
3. **검증 참조** — 각 문서의 `expected_readers` 필드가 코퍼스 대비 권한 매트릭스를
   자동 테스트할 수 있게 함

### 6.1 문서 스키마

각 항목은 다음 필드를 사용한다.

| 필드 | 필수 여부 | 설명 |
|---|---|---|
| `id` | 필수 | 고유 식별자 (예: `DOC-001`) |
| `title` | 필수 | 사람이 읽을 수 있는 문서명 |
| `category` | 필수 | hr, security, tech, finance, marketing, legal 중 하나 |
| `sub_type` | 필수 | 점 구분 sub-type (예: `hr.policy`) |
| `sensitivity` | 필수 | Low / Medium / High / Critical |
| `subject` | 조건부 | self-access 문서용 사용자 ID (hr.personnel, finance.expense) |
| `project_id` | 조건부 | `tech.project`용 프로젝트 식별자 |
| `project_members` | 조건부 | 프로젝트 접근 가능한 사용자 ID 리스트 |
| `parties` | 조건부 | case 기반 접근(legal.*)용 사용자 ID 리스트 |
| `case_id` | 조건부 | 법무 문서의 case 식별자 |
| `stakeholders` | 조건부 | security.incident의 명시된 접근자 사용자 ID 리스트 |
| `severity` | 조건부 | security.incident용 (low / medium / high / critical) |
| `executive_briefed` | 조건부 | security.incident 임원 브리핑 여부 (boolean) |
| `disclosure_level` | 조건부 | legal.litigation용 (`executive_briefing` 등) |
| `tags` | 선택 | 횡단 접근용 보조 태그 (예: `security`) |
| `expected_readers` | 필수 | 해당 문서를 읽을 것으로 기대되는 페르소나 ID (테스트 검증용) |

카탈로그에서 참조되는 사용자 ID는 섹션 2에서 정의된 것과 일치한다:
`user_emp_001/002/003`, `user_tl_001`, `user_exec_001`, `user_sec_001`,
`user_ext_001`, `user_aud_001`, `user_hrs_001`.

### 6.2 카테고리별 카탈로그

#### 6.2.1 `hr` — Human Resources (8개 문서)

| ID | Title | Sub-type | 민감도 | 특수 속성 | Expected Readers |
|---|---|---|---|---|---|
| DOC-001 | Employee Handbook 2026 | `hr.policy` | Low | — | 전 인증 employee+ |
| DOC-002 | Leave Policy v3.2 | `hr.policy` | Low | — | 전 인증 employee+ |
| DOC-003 | Remote Work Guidelines | `hr.policy` | Low | — | 전 인증 employee+ |
| DOC-004 | 2026 Salary Band Reference | `hr.compensation` | High | — | executive, hr_specialist, auditor |
| DOC-005 | Bonus Structure FY2026 | `hr.compensation` | High | — | executive, hr_specialist, auditor |
| DOC-006 | Performance Review: user_emp_001 (2025) | `hr.personnel` | Critical | `subject: user_emp_001` | user_emp_001 (본인), hr_specialist, auditor |
| DOC-007 | Performance Review: user_tl_001 (2025) | `hr.personnel` | Critical | `subject: user_tl_001` | user_tl_001 (본인), hr_specialist, auditor |
| DOC-008 | Backend Engineer Hiring Pipeline Q4 2026 | `hr.recruitment` | Medium | — | hr_specialist, 채용 중인 team_lead (`is_hiring: true`), executive |

#### 6.2.2 `security` — Security & InfoSec (7개 문서)

| ID | Title | Sub-type | 민감도 | 특수 속성 | Expected Readers |
|---|---|---|---|---|---|
| DOC-009 | Password Policy v2.1 | `security.policy` | Low | — | 전 인증 employee+ |
| DOC-010 | Information Security Code of Conduct | `security.policy` | Low | — | 전 인증 employee+ |
| DOC-011 | INC-2026-08-001: Suspicious Login Attempt | `security.incident` | Critical | `severity: high`, `stakeholders: [user_exec_001]` | security_officer, user_exec_001 (stakeholder) |
| DOC-012 | INC-2026-09-003: Data Exfiltration Attempt | `security.incident` | Critical | `severity: critical`, `executive_briefed: true`, `stakeholders: [user_exec_001]` | security_officer, user_exec_001, auditor |
| DOC-013 | INC-2026-09-005: Insider Threat Investigation | `security.incident` | Critical | `severity: high`, `stakeholders: [user_sec_001]` | security_officer only (임원 브리핑 X) |
| DOC-014 | Q3 2026 Threat Landscape Brief | `security.threat_intel` | High | — | security_officer only |
| DOC-015 | SOC2 Type II Audit Report 2025 | `security.compliance` | High | `tags: [audit]` | security_officer, auditor |

#### 6.2.3 `tech` — Technology & Engineering (10개 문서)

| ID | Title | Sub-type | 민감도 | 특수 속성 | Expected Readers |
|---|---|---|---|---|---|
| DOC-016 | BWCorp Infrastructure Architecture v3 | `tech.architecture` | Medium | — | Tech 부서 employee+, executive (Tech 디비전) |
| DOC-017 | Microservices Communication Patterns | `tech.architecture` | Medium | — | Tech 부서 employee+ |
| DOC-018 | Payment API v2 Specification | `tech.api` | Low | — | 전 인증 employee+ |
| DOC-019 | SSO Authentication API Guide | `tech.api` | Low | — | 전 인증 employee+ |
| DOC-020 | Production Incident Response Playbook | `tech.runbook` | Medium | — | Tech 부서 employee+ |
| DOC-021 | Database Migration Procedures | `tech.runbook` | Medium | — | Tech 부서 employee+ |
| DOC-022 | Project Alpha: Architecture Design | `tech.project` | Medium | `project_id: project_alpha`, `project_members: [user_tl_001, user_emp_001, user_ext_001]` | 명시된 project members |
| DOC-023 | Project Beta: API Integration Guide | `tech.project` | Low | `project_id: project_beta`, `project_members: [user_emp_002, user_ext_001]` | 명시된 project members |
| DOC-024 | Project Gamma: Initial PRD | `tech.project` | High | `project_id: project_gamma`, `project_members: [user_exec_001, user_tl_001]` | 명시된 project members |
| DOC-025 | Project Delta: Sprint Planning | `tech.project` | Low | `project_id: project_delta`, `project_members: [user_emp_001, user_emp_003]` | 명시된 project members |

#### 6.2.4 `finance` — Finance & Accounting (8개 문서)

모든 `finance.*` 문서는 접근 시 강화된 감사 로깅을 트리거한다.

| ID | Title | Sub-type | 민감도 | 특수 속성 | Expected Readers |
|---|---|---|---|---|---|
| DOC-026 | 2026 Annual Budget Plan | `finance.budget` | High | — | executive, auditor, finance 부서 |
| DOC-027 | Q4 2026 Departmental Budget Allocation | `finance.budget` | High | — | executive, auditor, finance 부서 |
| DOC-028 | 2025 Annual Financial Report (Audited) | `finance.statement` | Critical | — | executive, auditor, finance 부서 |
| DOC-029 | Q3 2026 P&L Statement | `finance.statement` | Critical | — | executive, auditor, finance 부서 |
| DOC-030 | Expense Report: user_emp_001 (2026-09) | `finance.expense` | Medium | `subject: user_emp_001` | user_emp_001 (본인), finance 부서, auditor |
| DOC-031 | Expense Report: user_emp_002 (2026-09) | `finance.expense` | Medium | `subject: user_emp_002` | user_emp_002 (본인), finance 부서, auditor |
| DOC-032 | Expense Report: user_tl_001 (2026-09) | `finance.expense` | Medium | `subject: user_tl_001` | user_tl_001 (본인), finance 부서, auditor |
| DOC-033 | 2025 Corporate Tax Filing | `finance.tax` | Critical | — | auditor, finance 부서 only |

#### 6.2.5 `marketing` — Marketing & Brand (6개 문서)

| ID | Title | Sub-type | 민감도 | 특수 속성 | Expected Readers |
|---|---|---|---|---|---|
| DOC-034 | Fall 2026 Campaign Plan | `marketing.campaign` | Low | — | 전 인증 employee+ |
| DOC-035 | New SaaS Product Launch Campaign | `marketing.campaign` | Low | — | 전 인증 employee+ |
| DOC-036 | BWCorp Brand Guidelines 2026 | `marketing.brand` | Low | — | contractor 포함 전 인증 사용자 |
| DOC-037 | Logo Usage Manual | `marketing.brand` | Low | — | contractor 포함 전 인증 사용자 |
| DOC-038 | 2026 IT Solutions Market Analysis | `marketing.research` | Medium | — | Marketing 부서, executive |
| DOC-039 | Competitive Landscape Q3 2026 | `marketing.research` | Medium | — | Marketing 부서, executive |

#### 6.2.6 `legal` — Legal & Compliance (6개 문서)

| ID | Title | Sub-type | 민감도 | 특수 속성 | Expected Readers |
|---|---|---|---|---|---|
| DOC-040 | ExternalCo Consulting Service Agreement | `legal.contract` | High | `parties: [user_exec_001, user_ext_001]` | Legal 부서, 명시된 parties |
| DOC-041 | Cloud Vendor MSA 2026 | `legal.contract` | High | `parties: [user_exec_001, user_tl_001]` | Legal 부서, 명시된 parties |
| DOC-042 | PIPA Compliance Report 2026 | `legal.regulatory` | High | — | Legal 부서, executive, auditor |
| DOC-043 | GDPR Applicability Legal Opinion | `legal.opinion` | Critical | `parties: [user_exec_001]`, `case_id: ADV-2026-014` | Legal 부서, 명시된 parties |
| DOC-044 | ExternalCo Dispute Case 2026-001 | `legal.litigation` | Critical | `case_id: CASE-2026-001`, `parties: [user_exec_001]`, `disclosure_level: executive_briefing` | Legal 부서, 명시된 parties, executive (브리핑 시) |
| DOC-045 | IP Infringement Defense Case 2025-007 | `legal.litigation` | Critical | `case_id: CASE-2025-007`, `parties: [user_tl_001]` | Legal 부서, user_tl_001 only |

### 6.3 패턴 검증 맵

이 표는 섹션 4의 각 권한 패턴을 어떤 특정 문서가 테스트하는지 교차 참조한다.
M2 구현 단계에서 각 행은 하나 이상의 자동 테스트 케이스로 변환된다.

| 권한 패턴 | 테스트 문서 | 기대 동작 |
|---|---|---|
| **메타데이터 없을 시 default-deny** | (합성 — 추가 예정) | 모든 사용자 거부, 검색 결과에서 제외 |
| **Self-access 카브아웃 (hr.personnel)** | DOC-006, DOC-007 | subject 사용자만 읽기; hr_specialist는 전체, employee는 본인만 |
| **Self-access 카브아웃 (finance.expense)** | DOC-030, DOC-031, DOC-032 | subject 사용자 읽기; finance 부서·auditor는 전체; 그 외 거부 |
| **횡단 ReBAC (security.incident)** | DOC-011, DOC-012, DOC-013 | security_officer 항상; 명시된 stakeholders; executive는 `executive_briefed: true`인 경우만 (DOC-012) |
| **Threat intel 제한** | DOC-014 | security_officer only; auditor도 거부 |
| **프로젝트 스코프** | DOC-022, DOC-023, DOC-024, DOC-025 | 명시된 `project_members`만; contractor(user_ext_001)는 DOC-022 + DOC-023 접근 가능, DOC-024 + DOC-025 거부 |
| **강화 감사 로깅 (finance)** | DOC-026 ~ DOC-033 | 역할 무관 모든 접근이 감사 메타데이터와 함께 로깅 |
| **Case 기반 parties (legal.contract)** | DOC-040, DOC-041 | 명시된 parties + Legal 부서만 |
| **Case 기반 parties (legal.litigation)** | DOC-044, DOC-045 | 명시된 parties + Legal 부서만; DOC-044는 disclosure_level로 executive도 가시 |
| **폭넓은 베이스라인 (marketing.brand)** | DOC-036, DOC-037 | contractor 포함 전 인증 사용자 |
| **Compensation 제한** | DOC-004, DOC-005 | 다른 hr.* 접근권이 있더라도 employee/team_lead/contractor는 거부 |
| **Contractor 시간 만료** | (세션 레벨 테스트 — Rule 4) | `NOW() > user.end_date` 시 모든 접근 거부 |
| **감사 로깅 wrap (auditor)** | user_aud_001이 접근한 모든 문서 | grant와 함께 감사 로그 엔트리 생성 |

### 6.4 커버리지 검증

| Category × Sub-type | 문서 수 | 커버리지 |
|---|---|---|
| `hr.policy` | 3 | ✅ |
| `hr.compensation` | 2 | ✅ |
| `hr.personnel` | 2 | ✅ |
| `hr.recruitment` | 1 | ✅ |
| `security.policy` | 2 | ✅ |
| `security.incident` | 3 | ✅ |
| `security.threat_intel` | 1 | ✅ |
| `security.compliance` | 1 | ✅ |
| `tech.architecture` | 2 | ✅ |
| `tech.api` | 2 | ✅ |
| `tech.runbook` | 2 | ✅ |
| `tech.project` | 4 | ✅ |
| `finance.budget` | 2 | ✅ |
| `finance.statement` | 2 | ✅ |
| `finance.expense` | 3 | ✅ |
| `finance.tax` | 1 | ✅ |
| `marketing.campaign` | 2 | ✅ |
| `marketing.brand` | 2 | ✅ |
| `marketing.research` | 2 | ✅ |
| `legal.contract` | 2 | ✅ |
| `legal.regulatory` | 1 | ✅ |
| `legal.opinion` | 1 | ✅ |
| `legal.litigation` | 2 | ✅ |
| **총** | **45** | **24/24 sub-type 커버됨** |

## 7. Future Extensions

본 명세에서 의도적으로 미뤄둔 항목들. 구현 우선순위로 정렬됨. 각각은 완전한 프로덕션
시스템의 일부로 인정되지만 범위 관리를 위해 M1–M4에서 제외되었다.

### 7.1 사용자당 다중 역할

사용자가 여러 역할을 동시에 가지며, 유효 권한은 역할별 부여의 합집합이 되도록
허용. 필요사항:
- JWT 스키마 변경 (`role: ...` 단수가 아닌 `roles: [...]`)
- 어떤 역할 조합도 최소 권한 원칙을 위반하지 않는지 매트릭스 재평가

**연기 근거**: 대부분의 엔터프라이즈는 이를 *"사용자가 그룹 A와 그룹 B에 속함"*으로
모델링하지 *"사용자가 역할 A와 역할 B를 가짐"*으로 모델링하지 않는다. M1 단일 역할이
데이터 명세를 평가 가능하게 유지한다.

### 7.2 Contractor를 넘어선 시간 제약

현재는 `contractor`만 start/end date 검증을 강제한다. 실 시스템에서는 다음으로 확장:
- 시간대 제한 (예: compensation 문서는 업무 시간에만 접근 가능)
- 신규 입사자의 수습 기간 (`employee` + `probation_until`)
- 프로젝트 종료 시 자동 회수

### 7.3 실 IDP 통합

FastAPI mock JWT 발급기를 production-grade OIDC 제공자로 교체.
**M4 stretch goal로 계획됨**:
- 1차 후보: **Keycloak** (오픈소스, Docker 배포 가능, OIDC/SAML 지원)
- 매핑 계획: BWCorp 역할 → Keycloak realm role; 페르소나 속성 → Keycloak 사용자 속성
- 권한 추상화 계층이 IdP-agnostic임을 시연 — 클레임이 ADFS, Keycloak, Auth0, Okta
  어디에서 오든 동일한 매트릭스와 규칙이 동작한다.

### 7.4 감사 로그에 대한 이상 탐지

감사 로그 위에서 동작하는 패턴 탐지. 별도의 LangGraph 서브그래프가 비동기로 트리거:
- 동일 사용자의 반복적 거부 질의 → 잠재적 prober
- 단일 부서 사용자의 부서 횡단 질의
- 주간 사용자의 비업무시간 접근
- 대량 검색 패턴 (잠재적 exfiltration)

### 7.5 문서 분류 자동화

현재 문서는 `category`와 `sub_type`을 수동 태깅한다. 향후에는 LLM 기반 분류기가
수집 시점에 분류를 제안하고, 고민감도 카테고리에 대해서는 사람의 승인 게이트를 두는
형태가 가능하다.

### 7.6 폴더 / 계층 기반 권한

현재 모델은 평면적 — 권한이 문서 단위로 평가된다. 실 ECM 시스템(SharePoint, Google Drive)은
폴더 계층을 통해 권한을 전파한다. 상속을 추가하려면 권한 엔진이 부모 폴더를 순회해야
하며, 이는 캐싱을 복잡하게 하지만 조직 규모의 관리를 가능하게 한다.

### 7.7 조직 간 페더레이션

BWCorp 직원이 파트너 조직의 RAG 시스템 문서에 접근(또는 그 역)하는 B2B 시나리오용.
표준 ABAC + SAML 페더레이션 패턴. 본 내부 중심 프로젝트의 범위 밖.

---

위 목록은 의도적으로 완전하지 않다. M1 설계 시점에서 가장 임팩트가 큰 확장들을
대표한다. 구현이 진척되면서(M2–M4) 추가 갭이 발견되어 이 목록에 추가될 수 있다.
