# Spec Templates

Use the appropriate template based on spec type. Copy the template, fill in every section.

**Scaling rule:** Match the spec's depth to the task's complexity. A one-day task needs Problem + Solution + Acceptance Criteria. A multi-week feature needs every section. Delete any section that genuinely doesn't apply — an honest short spec beats a padded long one.

---

## Template 1: Feature Spec (Full)

Use for: new user-facing capabilities, major enhancements, anything touching 3+ files.

```markdown
# Spec NNN: [Title]

**Status:** draft | review | approved | implementing | done | stale
**Phase:** v0.X
**Research deps:** [research/file.md section, ...]
**Depends on:** [Spec NNN (reason) -- omit if none]
**Blocks:** [Spec NNN (reason) -- omit if none]
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD

## Problem

<!-- Why does this need to be solved, and why now?
     Write from the user's perspective, not the system's. -->

## Goals

- Goal 1 (research/file.md) [VERIFIED]
- Goal 2
- Goal 3

## Non-Goals

- Non-goal 1 -- reason
- Non-goal 2 -- reason

## Solution

<!-- High-level approach. Focus on trade-offs. -->

## Core Specifications

**SPEC-001: [Behavior name]**

| Field | Value |
|-------|-------|
| Description | [What exactly happens] |
| Trigger | [What initiates this] |
| Input | [Required data/actions] |
| Output | [What user sees/gets] |
| Validation | [Input constraints] |
| Auth Required | [Yes/No] |

Acceptance Criteria:
- [ ] [Testable criterion -- binary pass/fail]
- [ ] [Another criterion]

## Edge Cases & Failure Modes

**EDGE-001: [Edge case name]**
- Scenario: [When this occurs]
- Expected behavior: [What should happen]
- Error message: "[Exact user-facing message]"
- Recovery: [How user resolves]

Standard edge cases to address:
- [ ] Empty states (no data yet)
- [ ] Invalid input (wrong format, too long, special chars, unicode)
- [ ] Boundary values (zero, negative, max int, empty string)
- [ ] Network failure (API timeout, connection lost, partial response)
- [ ] Concurrent actions (double-click, race conditions)
- [ ] Permission denied (not authenticated, wrong role, expired token)
- [ ] State transitions (cancel mid-operation, timeout during upload)

## API Contract [if applicable]

## Database Changes [if applicable]

| Table | Column | Type | Constraints | Notes |
|-------|--------|------|-------------|-------|
| [table] | [column] | [type] | [NOT NULL, FK, etc.] | [migration notes] |

## State Definitions [if UI involved]

| State | Visual Indicator | User Can... | System Shows... |
|-------|------------------|-------------|-----------------|
| Loading | [indicator] | [actions] | [display] |
| Empty | [indicator] | [actions] | [message] |
| Error | [indicator] | [actions] | [message] |
| Success | [indicator] | [actions] | [confirmation] |

## Implementation Notes
## Alternatives Considered
## Observability [if runs in production]
## Rollback Plan [if applicable]
## Open Questions
## Acceptance Criteria
```

---

## Template 2: API Spec

Use for: new endpoints, API contract changes, webhook definitions.

```markdown
# Spec NNN: [API Feature Name]

**Status:** draft | review | approved | implementing | done | stale
**Phase:** v0.X
**Research deps:** [research/file.md section, ...]
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD

## Problem
## Endpoints

### `METHOD /v1/path`

**Auth:** [Required/Optional/None] -- [token type]
**Rate limit:** [requests/minute]

**Error Responses:**

| Status | Code | Message | When |
|--------|------|---------|------|
| 400 | INVALID_INPUT | "[exact message]" | [condition] |

## Edge Cases & Failure Modes
## Alternatives Considered
## Observability
## Performance
## Non-Goals
## Acceptance Criteria
```

---

## Template 3: Schema Spec

Use for: database migrations, new tables, column changes.

```markdown
# Spec NNN: [Schema Change Name]

**Status:** draft | review | approved | implementing | done | stale

## Problem
## Schema Changes

### New Tables

#### `table_name`

| Column | Type | Constraints | Default | Notes |
|--------|------|-------------|---------|-------|
| id | UUID | PK | gen_random_uuid() | |
| created_at | TIMESTAMPTZ | NOT NULL | NOW() | |
| updated_at | TIMESTAMPTZ | NOT NULL | NOW() | |

### Modified Tables

## Migration Strategy

- [ ] Migration is reversible (has DOWN migration)
- [ ] Backfill strategy defined for existing rows
- [ ] No locking on large tables (online DDL or batched)

## Rollback Plan
## Data Integrity
## Alternatives Considered
## Acceptance Criteria
```

---

## Template 4: Integration Spec

Use for: external service connections (APIs, OAuth, webhooks).

```markdown
# Spec NNN: [Integration Name]

## Problem
## Solution (data flow diagram)
## Authentication
## API Calls
## Webhooks [if applicable]
## Failure Modes

| Failure | Detection | Recovery | User Impact |
|---------|-----------|----------|-------------|

## Security
## Observability
## Rollback Plan
## Alternatives Considered
## Acceptance Criteria
```

---

## Template 5: Bug Fix Spec (Lightweight)

Use for: complex bugs that need investigation before fixing. Skip for obvious bugs.

```markdown
# Spec NNN: Fix [Bug Title]

**Status:** draft | implementing | done
**Phase:** current
**Created:** YYYY-MM-DD

## Bug Description

- **Reported:** [how -- user report, test failure, monitoring]
- **Impact:** [who is affected, how badly]
- **Frequency:** [always / intermittent / rare]

## Reproduction Steps

1. [Step]
2. [Step]
3. [Step]

**Expected:** [what should happen]
**Actual:** [what happens instead]

## Root Cause
## Fix Specification

**SPEC-001: [What the fix must do]**
- [ ] [Testable acceptance criterion]
- [ ] Regression test added to prevent recurrence

## Scope

- **Fix:** [exactly what changes]
- **Do NOT touch:** [what to leave alone]

## Rollback Plan [if production]
```

---

## Template Selection Guide

```
What are you building?

New user-facing feature?
  -> Template 1: Feature Spec (Full)

New or changed API endpoints (no UI)?
  -> Template 2: API Spec

Database migration or schema change?
  -> Template 3: Schema Spec

Connecting to an external service?
  -> Template 4: Integration Spec

Fixing a non-trivial bug?
  -> Template 5: Bug Fix Spec

Multiple of the above?
  -> Use Template 1 (Feature) and include the relevant
    sections from other templates (DB, API, Integration)
```
