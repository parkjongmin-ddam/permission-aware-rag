# BWCorp Permission-aware RAG: Data Specification

This document defines the scenario, personas, document categories, and permission matrix
for the permission-aware RAG system implemented in this project.

The data here is fictional. Personas and permission patterns are derived from realistic
enterprise IAM patterns the author has implemented in production (5+ years operating ADFS,
SAML, OIDC, and AD-based authorization at a large Korean conglomerate).

## 1. Scenario Overview

**BWCorp** is a fictional mid-sized IT solutions company in Korea, ~500 employees.
The company has the following organizational dimensions:

- **Departments**: HR, Security, Tech (Engineering + Infrastructure), Finance, Marketing, Legal
- **Org hierarchy**: Employee → Team Lead → Director → VP → C-level
- **Cross-functional roles**: Security Officers, Auditors operate across departments
- **External entities**: Contractors with project-scoped, time-bounded access

The scenario is designed to exhibit permission patterns that cannot be cleanly modeled
with simple RBAC (Role-Based Access Control), thereby motivating ReBAC (Relationship-Based)
and ABAC (Attribute-Based) extensions in the RAG retrieval layer.

## 2. Personas

Seven personas are defined to cover distinct permission patterns. Each persona is a
combination of a **role** (string identifier) and a set of **attributes** (key-value pairs).
Both will be encoded as claims in mock JWT tokens issued at runtime by the system's
authentication node.

### 2.1 Quick Reference

| Role | Pattern | Clearance | Access Mode | Scope |
|---|---|---|---|---|
| `employee` | RBAC baseline | 1 | R | Own department + self-access |
| `team_lead` | Hierarchical RBAC | 2 | R/W | Own team + own department |
| `executive` | Top-of-hierarchy | 4 | R/W | Division-wide |
| `security_officer` | Cross-functional (ReBAC) | 3 | R/W | All departments (security scope) |
| `contractor` | External (ABAC) | 0 | R | Project-scoped, time-bounded |
| `auditor` | Read-only audit | 3 | R only | Audit scope (mandatory logging) |
| `hr_specialist` | Department specialist | 2 (HR) / 1 (other) | R/W (HR) / R (other) | HR domain |

### 2.2 employee — Baseline RBAC

The default authenticated user. Has read access to documents within their own department
and "self" documents (own performance reviews, payslips, etc.) in HR.

```yaml
role: employee
attributes:
  department: tech            # one of: hr, security, tech, finance, marketing, legal
  clearance_level: 1
  team_name: backend
  location: kr
  user_id: user_emp_001
```

**Permission pattern**: Standard RBAC with department-based scope.

### 2.3 team_lead — Hierarchical RBAC

Manages a specific team within a department. Can access team-internal documents
(team planning, performance reviews of direct reports) plus everything an employee
in the same department can access.

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

**Permission pattern**: RBAC + hierarchy (direct_reports relationship for self-access docs).

### 2.4 executive — Top-of-Hierarchy

Senior leadership (Director / VP / C-level). Has division-wide visibility for strategic
documents. Does NOT automatically see security-sensitive operational documents
(those go through security_officer scope, not org hierarchy — this is intentional ReBAC).

```yaml
role: executive
attributes:
  division: tech              # tech, business, corporate
  clearance_level: 4
  executive_level: vp         # director, vp, cxo
  location: kr
  user_id: user_exec_001
```

**Permission pattern**: RBAC with high clearance, but NOT a superuser. Notable: an
executive of the Business division cannot see Tech division's internal architecture docs.

### 2.5 security_officer — Cross-functional (ReBAC)

Security/InfoSec personnel. Has cross-department access to security-related documents
regardless of which department originated them. Critical pattern: a junior security_officer
can have MORE access to a security incident report than an executive — because access
is determined by **relationship to the security domain**, not org hierarchy.

```yaml
role: security_officer
attributes:
  clearance_level: 3
  scope: ["all_departments"]
  specialization: incident_response   # incident_response, audit, policy, threat_intel
  location: kr
  user_id: user_sec_001
```

**Permission pattern**: ReBAC. Cannot be modeled cleanly as "high clearance employee" —
the relationship to the security function is what grants access.

### 2.6 contractor — External (ABAC)

External party (e.g., consulting firm employee) granted limited access for a specific
project, within a specific time window. Their access is defined entirely by attributes,
not by org hierarchy.

```yaml
role: contractor
attributes:
  company: ExternalCo
  project_scope: [project_alpha, project_beta]
  start_date: "2026-06-01"
  end_date: "2026-09-30"
  clearance_level: 0
  allowed_categories: [tech]          # explicit allow-list, not department-based
  user_id: user_ext_001
```

**Permission pattern**: Pure ABAC. The retrieval node must evaluate
`(now within [start_date, end_date]) AND (doc.project in project_scope)
AND (doc.category in allowed_categories)`.

### 2.7 auditor — Read-only Audit

Internal or external auditor (e.g., compliance, SOX, internal audit). Has READ access
to sensitive documents across departments, but cannot modify anything. Every access
is mandatorily logged with stronger metadata than other roles.

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

**Permission pattern**: Multi-dimensional. Demonstrates that permission isn't just
"who" but also "how" (R vs R/W) and "how it's traced" (audit logging level).

### 2.8 hr_specialist — Department Specialist (Horizontal)

HR professional with elevated access within the HR domain (e.g., compensation analyst,
recruiter, HR policy author). Different from team_lead: their elevation is **horizontal
(within a department)** rather than **vertical (within a team)**.

```yaml
role: hr_specialist
attributes:
  department: hr
  specialization: compensation    # compensation, recruitment, policy, benefits
  clearance_level: 2              # within HR; outside HR = 1
  cross_team_access: true         # within HR only
  location: kr
  user_id: user_hrs_001
```

**Permission pattern**: Demonstrates that the Role × Category matrix is non-uniform —
an `hr_specialist` accessing HR docs is treated very differently from accessing other
departments' docs.

### 2.9 Pattern Coverage Summary

| Permission Pattern | Persona(s) Demonstrating It |
|---|---|
| Standard RBAC | employee |
| Hierarchical RBAC | team_lead, executive |
| Cross-functional ReBAC | security_officer |
| Read-only with mandatory logging | auditor |
| Department-bounded specialization | hr_specialist |
| Attribute-Based + temporal + project-scoped | contractor |
| Self-access pattern (own data exception) | all roles (HR self-docs) |

This combination is deliberately designed so that **no single permission model
(pure RBAC, pure ReBAC, pure ABAC) can satisfy all access requirements**. The
retrieval layer must compose checks from multiple dimensions.

## 3. Document Categories

Six top-level categories cover the company's document landscape. Each document is
tagged with exactly one primary category, an optional sub-type, and additional
attributes (project_id, case_id, subject, etc.) used by the retrieval layer for
permission filtering.

### 3.1 Quick Reference

| Category | Sensitivity (typical) | Special Pattern |
|---|---|---|
| `hr` | Medium (mixed) | Self-access carve-out for own records |
| `security` | High | Cross-functional via security_officer |
| `tech` | Low–Medium | Often project-scoped |
| `finance` | High | Auditor primary scope, heightened logging |
| `marketing` | Low | Broadly accessible baseline |
| `legal` | Critical | Case-based ABAC (named parties) |

### 3.2 `hr` — Human Resources

HR policies, performance management, benefits, recruitment.

**Sub-types**:
- `hr.policy` — Company-wide HR policies (handbook, leave policy)
- `hr.compensation` — Salary bands, bonus structures
- `hr.personnel` — Individual employee records (performance reviews, payroll)
- `hr.recruitment` — Hiring pipelines, candidate evaluations

**Special pattern — Self-access carve-out**: Any authenticated user can read
`hr.personnel` documents where `doc.subject == user.user_id`, regardless of
other restrictions. This models the real-world reality that employees can
always see their own HR records.

### 3.3 `security` — Security & InfoSec

Security policies, incident reports, threat intelligence, audit findings.

**Sub-types**:
- `security.policy` — Acceptable use, password policy
- `security.incident` — Incident reports, RCA documents
- `security.threat_intel` — Threat landscape briefings
- `security.compliance` — SOC2 / ISO27001 documentation

**Special pattern — Cross-functional access**: A junior `security_officer` may
have MORE access to a `security.incident` document than a senior `executive`,
because access is granted by relationship to the security function, not by
hierarchy clearance. This is the core ReBAC pattern.

### 3.4 `tech` — Technology & Engineering

Architecture documents, API specifications, infrastructure runbooks, project docs.

**Sub-types**:
- `tech.architecture` — System architecture, design docs
- `tech.api` — API specifications, integration guides
- `tech.runbook` — Operational runbooks
- `tech.project` — Project-specific docs (always tagged with `project_id`)

**Special pattern — Project scoping**: `tech.project` documents carry a `project_id`
attribute. Contractors gain access only when their `project_scope` includes that
ID. This is also how cross-team Tech employees collaborate on shared projects.

### 3.5 `finance` — Finance & Accounting

Budgets, financial statements, expense reports, tax records.

**Sub-types**:
- `finance.budget` — Annual / quarterly budget documents
- `finance.statement` — Financial statements (P&L, balance sheet)
- `finance.expense` — Expense reports, T&E records (per-user)
- `finance.tax` — Tax filings, audit-related records

**Special pattern — Auditor primary scope + heightened logging**: This category
is the auditor persona's primary access target. Every access (read) by any user
is logged with extended metadata (audit_engagement_id when applicable, IP,
timestamp, retrieved doc IDs). `finance.expense` carries a self-access carve-out
similar to `hr.personnel`.

### 3.6 `marketing` — Marketing & Brand

Campaigns, brand guidelines, market research.

**Sub-types**:
- `marketing.campaign` — Campaign plans, materials
- `marketing.brand` — Brand guidelines, logos
- `marketing.research` — Market research reports

**Special pattern — Broadly accessible baseline**: The lowest-sensitivity category.
Most `marketing.brand` documents are readable by all authenticated users, including
contractors. Provides a useful baseline against which to compare more restrictive
categories.

### 3.7 `legal` — Legal & Compliance

Contracts, regulatory filings, legal opinions, litigation.

**Sub-types**:
- `legal.contract` — Commercial contracts, NDAs
- `legal.regulatory` — Regulatory filings, compliance reports
- `legal.opinion` — Legal advice memos
- `legal.litigation` — Litigation-related documents

**Special pattern — Case-based ABAC**: Many `legal` documents carry a `case_id`
and a `parties` list. Access requires either being on the legal team OR being
explicitly named in `parties`. This pattern cannot be modeled by role alone —
it depends on per-document attributes (the doc itself names who can see it).

### 3.8 Category × Sub-type Sensitivity Map

This table previews the inputs to the Permission Matrix in Section 4. *Sensitivity*
indicates the typical confidentiality level; *Default Reader Pool* is the baseline
set of personas who can read without additional attribute checks.

| Category | Sub-type | Sensitivity | Default Reader Pool |
|---|---|---|---|
| `hr` | `policy` | Low | All employees+ |
| `hr` | `compensation` | High | hr_specialist, executive |
| `hr` | `personnel` | Critical | Self + hr_specialist + auditor |
| `hr` | `recruitment` | Medium | hr_specialist + hiring team_lead |
| `security` | `policy` | Low | All employees+ |
| `security` | `incident` | Critical | security_officer + named stakeholders |
| `security` | `threat_intel` | High | security_officer |
| `security` | `compliance` | High | security_officer + auditor |
| `tech` | `architecture` | Medium | Tech department + project members |
| `tech` | `api` | Low | All employees+ |
| `tech` | `runbook` | Medium | Tech department |
| `tech` | `project` | Variable | Project members (any role) |
| `finance` | `budget` | High | Finance + executive + auditor |
| `finance` | `statement` | Critical | Finance + executive + auditor |
| `finance` | `expense` | Medium | Self + finance + auditor |
| `finance` | `tax` | Critical | Finance + auditor |
| `marketing` | `campaign` | Low | All employees+ |
| `marketing` | `brand` | Low | All employees+ contractor (limited) |
| `marketing` | `research` | Medium | Marketing + executive |
| `legal` | `contract` | High | Legal + named parties |
| `legal` | `regulatory` | High | Legal + executive + auditor |
| `legal` | `opinion` | Critical | Legal + named parties |
| `legal` | `litigation` | Critical | Legal + named parties + executive (limited) |

### 3.9 Pattern Coverage Summary

| Permission Pattern | Category Demonstrating It |
|---|---|
| Self-access exception | `hr.personnel`, `finance.expense` |
| Cross-functional override (ReBAC) | `security.incident`, `security.compliance` |
| Project-scoped (ABAC) | `tech.project` |
| Heightened audit logging | All `finance.*`, `security.compliance` |
| Case-based party listing (ABAC) | `legal.contract`, `legal.opinion`, `legal.litigation` |
| Broad baseline (low restriction) | `marketing.brand`, `marketing.campaign` |

The categories are designed so that **each major permission pattern from Section 2
is grounded in at least one concrete document category**. This pairing is what
makes Section 4's matrix non-trivial — it cannot be reduced to a simple
"role.clearance ≥ doc.clearance" check.

## 4. Permission Matrix

### 4.1 Access Notation

| Symbol | Meaning |
|---|---|
| `R` | Read access |
| `R/W` | Read and Write |
| `-` | No access (default deny) |
| `S` | Self-access only (`doc.subject == user.user_id`) |
| `P` | Project-scoped (`doc.project_id ∈ user.project_scope`) |
| `M` | Member-only (`user.user_id ∈ doc.parties`) |
| `C` | Conditional — see sub-type refinements in 4.3 |

All access by `auditor` triggers mandatory audit logging (Rule 5 in Section 4.4).

### 4.2 Default Access Matrix (Role × Category)

This is the BASELINE at the category level. Sub-type-specific overrides are in Section 4.3.
Conditional rules in Section 4.4 may grant access beyond what this table shows.

| Role | `hr` | `security` | `tech` | `finance` | `marketing` | `legal` |
|---|---|---|---|---|---|---|
| **employee** | C | R(policy) | R(own dept) + P | S(expense) | R | M |
| **team_lead** | C | R(policy) | R/W(own team) + P | S(expense) | R | M |
| **executive** | C | R(policy) | R(own division) | R(budget, statement) | R/W | R(regulatory) |
| **security_officer** | - | R/W | R(security-tagged) | R(compliance) | - | M(security-related) |
| **contractor** | - | - | P (read-only) | - | R(brand only) | - |
| **auditor** | R(personnel) | R(compliance) | - | R(all, logged) | - | R(regulatory) |
| **hr_specialist** | R/W | R(policy) | R(own dept) | - | R | - |

### 4.3 Sub-type Refinements

Where a sub-type's access differs from the category default in 4.2, the override is here.
If a sub-type is not listed, it inherits from 4.2.

#### 4.3.1 `hr.compensation`
| Role | Access |
|---|---|
| employee, team_lead, contractor | `-` |
| executive | `R` |
| hr_specialist | `R/W` |
| auditor | `R` (logged) |

#### 4.3.2 `hr.personnel`
| Role | Access |
|---|---|
| All roles | `S` (only `doc.subject == user.user_id`) |
| hr_specialist | `R/W` (all personnel docs) |
| auditor | `R` (logged) |

#### 4.3.3 `hr.recruitment`
| Role | Access |
|---|---|
| employee, contractor | `-` |
| team_lead | `R/W` only if `user.attributes.is_hiring == true` |
| hr_specialist | `R/W` |
| executive | `R` |

#### 4.3.4 `security.incident`
| Role | Access |
|---|---|
| All by default | `-` |
| security_officer | `R/W` |
| Named stakeholder | `R` (if `user.user_id ∈ doc.stakeholders`) |
| executive | `R` only if `doc.severity ∈ [critical]` AND `doc.executive_briefed == true` |

#### 4.3.5 `security.threat_intel`
| Role | Access |
|---|---|
| security_officer | `R` |
| All others | `-` |

#### 4.3.6 `security.compliance`
| Role | Access |
|---|---|
| security_officer | `R/W` |
| auditor | `R` (logged) |
| All others | `-` |

#### 4.3.7 `tech.project`
Access via project membership, not org hierarchy. See Conditional Rule 2 in 4.4.

#### 4.3.8 `finance.statement`, `finance.budget`, `finance.tax`
| Role | Access |
|---|---|
| employee, team_lead, hr_specialist | `-` |
| executive | `R` |
| auditor | `R` (logged) |
| Finance department personnel (attribute: `department == 'finance'`) | `R/W` |

#### 4.3.9 `legal.litigation`
| Role | Access |
|---|---|
| All by default | `M` (must be in `doc.parties`) |
| Legal department personnel | `R/W` |
| executive | `R` only if `doc.disclosure_level == 'executive_briefing'` |
| auditor | `R` if `doc.case_type` ∈ `auditor.audit_scope` (logged) |

### 4.4 Conditional Rules

These rules apply ACROSS categories. Evaluated in the order defined in 4.5.

#### Rule 1 — Self-Access Carve-out
```
IF doc.subject == user.user_id
   AND doc.category.sub_type IN ['hr.personnel', 'finance.expense']:
    ALLOW Read
```
Models the legal requirement that users can always see their own records.

#### Rule 2 — Project Membership
```
IF doc.project_id IS NOT NULL:
    IF user.user_id IN doc.project_members:
        ALLOW Read (or R/W per role)
    IF doc.project_id IN user.attributes.project_scope:
        ALLOW Read  # primary contractor path
```

#### Rule 3 — Named Parties (Case-Based)
```
IF doc.category == 'legal' AND doc.parties IS NOT NULL:
    IF user.user_id IN doc.parties:
        ALLOW Read
```

#### Rule 4 — Temporal Constraint
```
IF user.role == 'contractor':
    IF NOT (user.start_date <= NOW() <= user.end_date):
        DENY ALL (overrides everything else)
```
Applies to contractors only. Other roles' permissions are not time-bounded in this spec
(could be extended later).

#### Rule 5 — Audit Logging Enforcement
```
IF user.role == 'auditor':
    WRAP any granted access with:
        - log(audit_engagement_id, user_id, doc_id, timestamp, retrieved_chunks)
        - store in tamper-evident audit_log table
```

#### Rule 6 — Cross-functional Override (security_officer)
```
IF user.role == 'security_officer'
   AND (doc.category == 'security' OR doc.has_tag('security')):
    ALLOW Read (or R/W per 4.2)
# This OVERRIDES the default that org hierarchy would otherwise enforce.
```

### 4.5 Evaluation Order

The retrieval layer composes permission checks in this order. The **first rule that grants
access wins**; if no rule grants access, the document is excluded from results.

1. **Rule 4** (Temporal Constraint) — outright deny if expired
2. **Rule 6** (Cross-functional) — security_officer override
3. **Rule 1** (Self-Access) — universal carve-out
4. **Rule 2** (Project Membership) — for `tech.project` docs
5. **Rule 3** (Named Parties) — for `legal.*` docs with parties list
6. **Default Matrix (4.2)** with sub-type refinements (4.3)
7. **Rule 5** (Audit Logging Wrap) — applies on top of any grant for auditor

If multiple roles apply to a user (not standard, but possible), the **union of granted
permissions** is the effective permission.

### 4.6 Design Decisions

Key choices and the rationale behind them:

- **No global superuser.** Even C-level executives don't see `security.incident` by default.
  Security is a cross-functional dimension, not the top of a hierarchy. This is what
  motivates the ReBAC pattern in the retrieval layer.

- **Self-access is universal, not role-dependent.** Implemented as a Rule that fires for
  all roles. This mirrors GDPR/PIPA data subject rights and is one of the most commonly
  mismodeled patterns in naive RBAC systems.

- **Contractor access is additive-only.** Contractors have NO default access. Their
  permissions are defined entirely by `allowed_categories` and `project_scope` attributes.
  This is the safest baseline for external parties.

- **Auditor R/W is metadata-only.** Auditors do not modify operational documents. R/W
  refers to audit annotations, findings, and the audit_log table itself.

- **Department attribute matters more than role.** A user with `role: employee` and
  `department: finance` has different access from `role: employee` + `department: marketing`.
  This intentionally makes the matrix non-uniform and demonstrates that role alone is
  insufficient (pure RBAC limitation).

- **Conditional rules are precedence-ordered.** Evaluation order (4.5) matters because
  some rules grant (Rule 6) while others deny (Rule 4). The order is chosen so that
  hard denies (temporal expiry) win over grants.

## 5. Edge Cases

Real-world permission systems break in interesting ways at boundaries. The following
five cases are intentionally addressed in this spec to ensure the retrieval layer
behaves predictably (and securely) in their presence.

### 5.1 Documents with Missing Permission Metadata

**Scenario**: A document is ingested into the corpus without a `category` or `sub_type`
attribute, or with malformed metadata.

**Decision**: **Default-deny**. The retrieval layer treats undecorated documents as
inaccessible to all users, regardless of role. The ingestion pipeline must reject or
quarantine such documents rather than letting them flow into searchable storage.

**Rationale**: Default-allow on metadata gaps is the single most common cause of
permission breaches in real systems. Failing closed is safer than failing open.

### 5.2 Multi-tagged Documents (Cross-functional Content)

**Scenario**: A document genuinely belongs to multiple categories — e.g., an "HR Security
Awareness Policy" is both HR and Security. Or a "Q4 Financial Compliance Report" is both
Finance and Legal.

**Decision**: Each document has exactly **one primary category** (`doc.category`) plus
optional **secondary tags** (`doc.tags: [...]`). Permission evaluation uses primary
category for the matrix lookup; secondary tags are used for Conditional Rule 6
(security_officer override) and audit scoping.

**Rationale**: Forcing a primary category keeps the matrix evaluable. Tags handle
horizontal concerns (e.g., `security_officer` can read anything with `security` in
either category OR tags).

### 5.3 Conflict Resolution: Explicit Sub-type Deny vs Rule Grant

**Scenario**: Sub-type 4.3.5 says `security.threat_intel` is `-` for all roles except
`security_officer`. But Rule 6 (cross-functional override) grants security_officer
access to any `security.*` document. What if a separate rule (e.g., a future "executive
emergency briefing" rule) tries to grant an executive access to `security.threat_intel`?

**Decision**: **Explicit deny in sub-type refinements (4.3) wins over rule grants (4.4).**
A sub-type marked `-` for a role cannot be overridden by a conditional rule. The only
exception is Rule 1 (Self-Access) for `hr.personnel` and `finance.expense`, which is
applied universally before sub-type checks (per the evaluation order in 4.5).

**Rationale**: Predictability over flexibility. If new rules could override sub-type
denies, the matrix becomes harder to audit. To grant new access, the sub-type itself
must be amended.

### 5.4 Document Existence vs Content Visibility

**Scenario**: A user queries *"What was the breach last month?"*. The retrieval layer
finds 3 relevant `security.incident` documents, but the user (a regular employee) has
no access. Should the answer be:

- (a) "I have no information about that." (full denial — pretends docs don't exist)
- (b) "There are 3 relevant documents, but you don't have permission to view them." (existence leaked)
- (c) "I cannot answer that question." (generic refusal)

**Decision**: **(a) for default queries, (c) for queries that pattern-match high-sensitivity
categories (security, finance, legal litigation).** The Answer Node generates a generic
non-confirmation rather than acknowledging that hidden documents exist.

**Rationale**: Option (b) leaks the existence of sensitive documents — itself an
information disclosure. (c) is reserved for queries that strongly imply targeting
restricted categories, to avoid revealing the user's lack of access as a side channel.

**Implementation note**: This is implemented in the Answer Node (not Retrieval), since
Retrieval correctly returns the empty set; the differentiation happens at the response
generation step.

### 5.5 Information Leakage Through Query Patterns

**Scenario**: A user repeatedly queries with terms that match document titles they cannot
access. Even if no content is returned, the retrieval latency, embedding scores, or
LLM responses might leak structural information.

**Decision**: Out of full scope for this spec, but the following mitigations are
designed in:

- **Retrieval-level**: Permission filtering happens at the database query (not post-filter).
  The retriever does not even see filtered-out documents, eliminating timing differences.
- **Logging-level**: All queries (including those returning empty results) are logged with
  the user's role and query text. Anomaly detection on these logs is a Future Extension
  (Section 7).
- **Rate-limiting**: Repeated high-sensitivity queries from a low-clearance user trigger
  a soft warning to the Audit Logger. Not implemented in M1 but designed for.

**Rationale**: Side-channel attacks on RAG systems are an emerging research area
(e.g., embedding inversion, prompt-based extraction). A production-grade system
must address them; this spec acknowledges the threat surface without claiming to
fully solve it.

### 5.6 Multiple Roles Per User (Future Consideration)

**Scenario**: A user is both `team_lead` AND `security_officer`. How are their permissions
composed?

**Decision (current spec)**: A single primary role per user. Multi-role support is a
**Future Extension** (Section 7). If implemented, the **union of granted permissions**
applies (per the closing note in 4.5).

**Rationale**: Keeping single-role-per-user simplifies the M1/M2 implementation. Most
real organizations resolve multi-role by issuing the user different JWTs for different
contexts (e.g., "act as security_officer for this task") rather than encoding all roles
in one token.

## 6. Sample Documents

*This section catalogs 30–50 representative documents covering all category × sub-type
combinations defined in Section 3, with concrete permission metadata illustrating the
patterns in Section 4. The catalog is generated in a separate work block and tracked
in the M1 milestone — see project README.*

## 7. Future Extensions

Items deliberately deferred from this specification, ranked roughly by implementation
priority. Each is acknowledged as part of a complete production system but excluded
from M1–M4 to keep scope manageable.

### 7.1 Multi-role Per User

Allow users to hold multiple roles simultaneously, with effective permissions as the
union of role-derived grants. Requires:
- JWT schema change (`roles: [...]` instead of single `role: ...`)
- Matrix re-evaluation to verify no role combination violates least-privilege

**Rationale for deferral**: Most enterprises model this as "user holds Group A and
Group B" rather than "user has Role A and Role B". M1 single-role keeps the data
spec evaluable.

### 7.2 Temporal Constraints Beyond Contractors

Currently only `contractor` enforces start/end date validation. Real systems extend
this to:
- Time-of-day restrictions (e.g., compensation docs accessible during business hours only)
- Probationary periods for new hires (`employee` + `probation_until`)
- Project-end auto-revocation

### 7.3 Real IDP Integration

Replace the FastAPI mock JWT issuer with a production-grade OIDC provider.
**Planned for M4 as a stretch goal**:
- Primary candidate: **Keycloak** (open-source, Docker-deployable, supports OIDC/SAML)
- Mapping plan: BWCorp roles → Keycloak realm roles; persona attributes → Keycloak
  user attributes
- Demonstrates that the permission abstraction layer is IdP-agnostic — the same
  matrix and rules work whether claims come from ADFS, Keycloak, Auth0, or Okta

### 7.4 Anomaly Detection on Audit Logs

Pattern detection on top of the audit log, implementable as a separate LangGraph
subgraph triggered asynchronously:
- Repeated denied queries from same user → potential probing
- Cross-department queries by single-department users
- Off-hours access by daytime users
- Bulk retrieval patterns (potential exfiltration)

### 7.5 Document Classification Automation

Currently documents are manually tagged with `category` and `sub_type`. A future
enhancement would use an LLM-based classifier to suggest classifications at ingestion
time, with human approval gates for high-sensitivity categories.

### 7.6 Folder / Hierarchy-based Permissions

Current model is flat — permissions are evaluated per document. Real ECM systems
(SharePoint, Google Drive) propagate permissions through folder hierarchies. Adding
inheritance requires the permission engine to traverse parent folders, complicating
caching but enabling management at organizational scale.

### 7.7 Cross-organization Federation

For B2B scenarios where BWCorp employees access documents in partner organizations'
RAG systems (or vice versa). Standard ABAC + SAML federation pattern. Explicitly
out of scope for this internal-focused project.

---

The above list is intentionally not exhaustive. It represents the most impactful
extensions visible from the M1 design perspective. As implementation progresses
(M2–M4), additional gaps may emerge and be added to this list.
