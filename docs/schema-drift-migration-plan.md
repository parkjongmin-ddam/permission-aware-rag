# Schema Migration: Sensitivity-Based RBAC

**Status**: Ready for execution (M4.0)
**Discovered**: 2026-05-20, M3.3 RAGAS evaluation
**Plan revised**: 2026-05-20 (added stepwise commit ordering, eval success/abort criteria, disclosure_level fix, hardening items separated as M4.0.5)
**Owner**: parkjongmin-ddam

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

**For M3 (completed)**: did not patch the matrix in-place.

Rationale:
- The drift is real and the eval correctly surfaces it. Patching by ad-hoc mapping (`marketing.public → marketing.research`) would conceal the drift without resolving the underlying tension.
- The fix is a non-trivial schema change with data implications. Outside M3 scope.
- The discovery is itself a portfolio artifact demonstrating self-validating systems.

**For M4.0 (this migration)**: introduce a `sensitivity` field on documents, orthogonal to `sub_type`. Rewrite the RBAC matrix as `role → allowed sensitivities`. This expresses the original design intent correctly.

## Target Schema

`sensitivity` is conceptually orthogonal to `sub_type`. In the current 45-doc dataset the mapping is deterministic (every `hr.policy` is `public`, every `legal.litigation` is `privileged`), but the two fields are kept separate so future cases can diverge — e.g., a normally-`internal` `tech.architecture` doc could be elevated to `restricted` for one specific design that touches unreleased acquisitions.

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
| `legal.litigation` | privileged | attorney-client privilege default — also requires `disclosure_level: privileged` marker (see Step 1) |

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

**Ordering principle**: code lands first in a dormant state, data lands second, the switch is flipped last. This ensures the system is never observed in a half-migrated state where data uses the new vocabulary but rules still reference the old.

1. **Add `sensitivity_rule` to code (dormant)** (~10min)
   - Add `sensitivity_rule` function to `permission/rules.py` per the spec above.
   - Add the new sensitivity-keyed `ROLE_DEFAULTS` matrix alongside the old one (rename old to `LEGACY_ROLE_DEFAULTS` for the duration of migration).
   - **Do NOT modify `permission/policy.py:RULES`** yet — the new rule exists but is not wired in. System behavior is identical to pre-migration.
   - Commit: `feat(rules): add sensitivity_rule (dormant, not yet wired)`

2. **Add sensitivity to data** (~15min)
   - `data/documents.yaml`: add `sensitivity:` field to each of 45 docs per the mapping table.
   - For DOC-044 and DOC-045 (the two `legal.litigation` documents), also add `disclosure_level: privileged`. This was an audit_rule design gap discovered in M3 — the rule checks for this marker but the data lacked it.
   - Commit: `data: add sensitivity field + privileged disclosure markers`

3. **Update DB schema and re-ingest** (~10min)
```sql
ALTER TABLE documents ADD COLUMN sensitivity TEXT;
```
   Backfill via re-ingest: `uv run python scripts/ingest.py`
   - Verify with: `SELECT sub_type, sensitivity, COUNT(*) FROM documents GROUP BY 1,2 ORDER BY 1;`
   - All 45 rows should have non-null sensitivity.
   - Commit: `db: add sensitivity column (re-ingest backfill)`

4. **Pre-flight: predict eval impact** (~10min)
   Before flipping the switch, write down the expected eval delta in a scratch note:
   - TC-013, TC-014, TC-016, TC-017 (current Truth=0 cases): predict whether each gains non-empty Truth after migration. Reasoning per case.
   - TC-005 sec_001 × DOC-013 (current recall loss): predict whether new matrix keeps or changes this case's outcome.
   - TC-009 × aud_001 × DOC-044 (privileged litigation): with `disclosure_level: privileged` now present, audit_rule should explicitly DENY. Predict eval will reflect this.
   - This prediction is a self-check that the change is understood before it's applied. No code edits in this step.

5. **Flip the switch** (~5min)
   - `permission/policy.py:RULES`: replace `rbac_default` with `sensitivity_rule`.
   - Delete `LEGACY_ROLE_DEFAULTS` (no longer referenced).
   - Commit: `feat(policy): switch rbac_default → sensitivity_rule`

6. **Validate with eval** (~10min)
   - `uv run python scripts/eval_retrieval.py`
   - Compare against M3.3 baseline and against the Step 4 predictions.
   - **Success criteria**:
     - Truth=0 cases: reduce from 4 to ≤2 (i.e., TC-013, 014, 016, 017 mostly resolve)
     - F1: stable or improved vs M3.3 baseline (0.560)
     - Eligible cases: increase from 28 (out of 52) toward 32+
   - **Abort criteria**:
     - F1 drops below 0.50 → migration is making the system worse; halt and review the mapping table
     - Step 4 predictions diverge from actual results in unexpected ways → investigate before continuing
   - Document both pre- and post-migration eval results in commit message.

7. **Update test dataset if needed** (~10min)
   - Re-label any case whose Truth set depended on the old matrix.
   - Most cases should not require changes since Truth is computed via `can_read()` from the live policy.
   - Commit (if any changes): `eval: relabel cases affected by sensitivity migration`

**Total estimated effort**: ~70 minutes engineering + ~20 minutes review.

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

### Adjacent work tracked separately

Two M3-era hardening items are intentionally NOT bundled into this migration to keep the commit history clean:

- **JWT_SECRET_KEY length** — currently 23 bytes, triggers `InsecureKeyLengthWarning`. Replace with 32+ byte random value. Tracked as M4.0.5 (pre-deployment hardening), should be done via Secrets Manager during M4.1 deployment work, not here.
- **Pydantic `extra="forbid"` strict mode** — silent kwarg drops (e.g., `reranker_score` vs `rerank_score`) caused real debugging time in M3. Add `model_config = ConfigDict(extra="forbid")` to all Pydantic models. Tracked as M4.0.5, separate commit from the schema migration.

## References

- Original drift discovery: M3.3 eval run, 2026-05-20
- Eval harness: `scripts/eval_retrieval.py`
- Test dataset: `eval/dataset.yaml` (18 cases × 52 persona-case pairs)
- Affected code: `src/permission_aware_rag/permission/rules.py`
- Affected data: `data/documents.yaml`