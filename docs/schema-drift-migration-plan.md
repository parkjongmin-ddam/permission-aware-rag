# Schema Migration: Sensitivity-Based RBAC

**Status**: Deferred to M4+
**Discovered**: 2026-05-20, M3.3 RAGAS evaluation
**Owner**: TBD

## Context

During M3.3 evaluation, the harness automatically surfaced a schema drift between two layers of the access control system:

- **Matrix layer** (`src/permission_aware_rag/permission/rules.py:ROLE_DEFAULTS`): designed with **sensitivity-based** sub_type vocabulary — `.handbook`, `.public`, `.documentation`, `.internal`, `.training`, `.audit`, `.forecast`. These describe *exposure levels*.

- **Data layer** (`data/documents.yaml`): instantiated with **topic-based** sub_type vocabulary — `.policy`, `.compensation`, `.recruitment`, `.architecture`, `.api`, `.budget`, `.campaign`, `.brand`, `.research`, `.regulatory`, `.opinion`, `.litigation`. These describe *content domains*.

Net effect:
- ~9 matrix entries reference sub_types that don't exist in data (dead entries)
- ~13 data sub_types have no role assignment (default-denied unless an ABAC rule applies)
- The eval surfaces this as elevated `Truth=0` rates in cases where access seems intuitively warranted (e.g., engineer querying `tech.architecture`)

This is a textbook IAM antipattern — *policy vocabulary drift* — where access policy and the data it governs were designed in separate iterations under different abstractions.

## Decision

**For M3 (current milestone)**: do not patch the matrix in-place.

Rationale:
- The drift is real and the eval correctly surfaces it. Patching by ad-hoc mapping (`marketing.public → marketing.research`) would conceal the drift without resolving the underlying tension.
- The fix is a non-trivial schema change with data implications. Outside M3 scope.
- The discovery is itself a portfolio artifact demonstrating self-validating systems.

**For M4+ (production path)**: introduce a `sensitivity` field on documents, orthogonal to `sub_type`. Rewrite the RBAC matrix as `role → allowed sensitivities`. This expresses the original design intent correctly.

## Target Schema

### Document additions

Add to each document in `data/documents.yaml`:

```yaml
sensitivity: public | internal | restricted | privileged
```

Definitions:
- **public** — readable by all employees and contractors. No business reason to restrict (e.g., policies everyone must comply with, brand guidelines).
- **internal** — restricted to employees. Default for most operational/work product documents.
- **restricted** — restricted to specific roles. Default for personal data, financial details, security operations.
- **privileged** — restricted beyond restricted (e.g., attorney-client communications, executive-only strategic docs).

### Suggested mapping for current documents

| Sub_type | Sensitivity | Reasoning |
|---|---|---|
| `hr.policy` | public | mandatory reading for all employees |
| `hr.compensation` | restricted | comp data is need-to-know |
| `hr.personnel` | restricted | personal data — privacy |
| `hr.recruitment` | internal | hiring teams and HR |
| `security.policy` | public | mandatory awareness for all |
| `security.incident` | restricted | handled by `incident_rule` |
| `security.threat_intel` | restricted | security operations only |
| `security.compliance` | restricted | audit + security domain |
| `tech.runbook` | internal | engineering operations |
| `tech.architecture` | internal | engineering + senior staff |
| `tech.api` | internal | engineering contract docs |
| `tech.project` | restricted | handled by `project_rule` |
| `finance.budget` | restricted | finance + executive |
| `finance.statement` | restricted | executive + audit |
| `finance.expense` | restricted | handled by `self_access` + `audit_rule` |
| `finance.tax` | privileged | executive + audit only |
| `marketing.campaign` | internal | marketing operations |
| `marketing.brand` | public | brand compliance for all employees |
| `marketing.research` | internal | competitive intelligence |
| `legal.contract` | restricted | handled by `parties_rule` |
| `legal.regulatory` | internal | compliance reference for all relevant roles |
| `legal.opinion` | restricted | legal advisory |
| `legal.litigation` | privileged | attorney-client privilege default |

### Matrix rewrite

```python
ROLE_DEFAULTS: dict[str, frozenset[str]] = {
    "employee":         frozenset({"public"}),
    "team_lead":        frozenset({"public", "internal"}),
    "executive":        frozenset({"public", "internal", "restricted"}),
    "security_officer": frozenset({"public", "internal", "restricted"}),
    "hr_specialist":    frozenset({"public", "internal", "restricted"}),
    "contractor":       frozenset({"public"}),
    "auditor":          frozenset(),  # audit_rule exclusively
}
```

### New rule

Replace `rbac_default` with `sensitivity_rule`:

```python
def sensitivity_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """Role-based access by document sensitivity level.

    Replaces the legacy sub_type-keyed ROLE_DEFAULTS matrix. Each role
    declares the maximum sensitivity it can read by default; more
    specialized access still flows through ABAC rules upstream.
    """
    sensitivity = document.get("sensitivity")
    if sensitivity is None:
        return None  # documents without sensitivity → no default access

    allowed = ROLE_DEFAULTS.get(principal.role, frozenset())
    if sensitivity in allowed:
        return PolicyDecision.allow(
            rule_name="sensitivity",
            reason=(
                f"role {principal.role} reads {sensitivity} documents "
                f"(sub_type={document.get('sub_type')})"
            ),
        )
    return None
```

## Migration Steps

1. **Add sensitivity to data** (~15min)
   `data/documents.yaml`: add `sensitivity:` field to each of 45 docs per the mapping table.

2. **Update DB schema** (~10min)
```sql
   ALTER TABLE documents ADD COLUMN sensitivity TEXT;
```
   Backfill via re-ingest: `uv run python scripts/ingest.py`

3. **Replace `rbac_default` with `sensitivity_rule`** (~15min)
   - Add `sensitivity_rule` to `permission/rules.py`
   - Update `permission/policy.py:RULES` list to use new rule
   - Update `ROLE_DEFAULTS` to sensitivity-keyed frozensets
   - Delete obsolete sub_type entries

4. **Validate with eval** (~10min)
   - `uv run python scripts/eval_retrieval.py`
   - Compare against M3.3 baseline: F1 0.464 → 0.560
   - Expected outcome: fewer `Truth=0` cases, F1 stable or improved

5. **Update test dataset if needed** (~10min)
   - Any case whose Truth set depended on the old matrix may need relabeling

**Total estimated effort**: ~60 minutes engineering + ~30 minutes review.

## Risks

- **Sensitivity assignment is a policy decision** — assigning each existing doc to a sensitivity tier is judgment, not mechanical. Some calls are clear (DOC-006 hr.personnel = restricted), others arguable (marketing.research could be internal or restricted). Get policy sign-off before bulk update.

- **Eval baseline shift** — F1 numbers will change after migration. Document both pre- and post-migration baselines so blog narratives remain auditable.

- **Backward compatibility** — documents without `sensitivity` field will receive `None` from `sensitivity_rule` and fall through to default-deny. Migration must be atomic across all 45 docs.

## Rollback

Revert `permission/policy.py:RULES` to include `rbac_default`. The sensitivity column on documents is harmless if unused. Total rollback time: ~5 minutes.

## Out of Scope

- Field-level sensitivity (e.g., redacting specific fields within a doc).
- Time-bound sensitivity (docs that become public after embargo).
- User-driven sensitivity tagging (user marks their own docs).
- Sensitivity inheritance from parent documents.

These are valid future considerations but require deeper schema work and are not part of this migration.

## References

- Original drift discovery: M3.3 eval run, 2026-05-20
- Eval harness: `scripts/eval_retrieval.py`
- Test dataset: `eval/dataset.yaml` (18 cases × 52 persona-case pairs)
- Affected code: `src/permission_aware_rag/permission/rules.py`
- Affected data: `data/documents.yaml`