# AVO v1 Evaluator and Leakage Input Review

**Review target:** `origin/fm/holusight-avo-setup-v1` at
`5679a8ba2e1288e14a3b01907699b467756c933c`

**Review type:** bounded, committed-input review; no trials, G2, hidden holdout, telemetry,
or laptop setup accessed.
**Status:** findings only — valid trials remain paused.

## Method and scope

Reviewed only the ten files introduced by the target commit, principally:

- `docs/avo/trial-manifest.v1.json` and its schema;
- `docs/avo/schemas/ledger.schema.json` and `checkpoint.schema.json`;
- `docs/avo/leakage-boundary.md`, `scoring-control-policy.md`, and `mini-bootstrap.md`.

The manifest's canonical self-hash is valid. This confirms byte-consistent manifest
content, not that a fetched manifest is the authorized commit or that any runtime
input complies with the policy.

## Enforced input properties

| Control | Input-level result |
|---|---|
| Required trial fields | Enforced by the ledger schema, including `purpose_id`, `control`, `lineage_parent`, and `decision_informed`. |
| Decision-informed value | Enforced as one of `calibration`, `product_improvement`, `supervisor_directive`, or `gate_recovery`. |
| One intervention object | An `intervention` object is required and closed to `kind`, `summary`, and `digest`. |
| Control object | A closed `control` object with `kind` and digest is required. |
| Evaluator record | Per-row evaluator and method-config digests are required; checkpoints require one evaluator digest. |
| Checkpoint manifest field | A syntactically valid `manifest_sha256` is required. |

These are shape checks. The target commit contains no executor or cross-record validator
to bind the values to the frozen manifest, a candidate, a control, or each other.

## Acceptance paths that defeat stated controls

1. **Evaluator is not pinned.** The manifest lists `evaluator` as an identity-binding
   category but contains no evaluator or method-config digest to compare. The ledger
   accepts any two valid SHA-256 strings, and the checkpoint can report a different
   one. A changed evaluator can therefore be recorded as valid rather than rejected.

2. **Candidate and evaluator are not separated.** `intervention.kind` permits
   `evaluator_method`; there is no candidate-subject identity, evaluator-subject
   identity, or rule tying an intervention to one of them. The arbitrary `purpose_id`
   does not constrain this to Phase A. A candidate change and evaluator change can be
   represented by opaque digests without a machine-checkable separation.

3. **Purpose coverage is nominal.** `purpose_id` only matches
   `^[a-z0-9._-]+$`; it is not an enum, registered-purpose reference, or mapping to
   experiment range/phase. A purpose-free-in-effect value such as `arbitrary-purpose`
   passes. `decision_informed` is present and enumerated, but has no reference to a
   recorded decision, purpose, or lane phase.

4. **One-intervention and matched-control claims are not verifiable.** A single
   object cannot prove its digest/summary contains one atomic change. `control.digest`
   need not equal a parent, baseline, candidate-matched subject, suite, corpus,
   evaluator, ordering, or seed. `lineage_parent` is an unconstrained string, so an
   unrelated parent passes.

5. **Protected gates are declarative.** A row needs only one arbitrary gate string;
   it need not include every manifest-frozen gate or report their boolean results.
   `hard_constraint_violations` is optional and a `completed`/`kept` row may contain
   it. The policy's gate-first decision rule is therefore not schema-enforced.

6. **Prompt, ordering, and hidden-input artifacts can be accepted.** The ledger's
   bounded text fields (`hypothesis`, `target_failure_mode`, `intervention.summary`,
   `expected_effect`, `falsifier`, and `notes`) can contain hidden query/prompt or
   corpus text. The policy's forbidden-key-name scan is not a JSON Schema constraint,
   and no schema binds an input/suite digest, prompt template digest, ordering/permutation
   digest, or ordering seed. Opaque evaluator/config digests cannot establish those
   properties.

7. **Proxy metrics can be accepted.** `trial.metrics` permits any property name with
   a number. It does not restrict metrics to the manifest primary metrics, require the
   hard constraints, or encode the scoring decision. A row containing only
   `unrelated_proxy` is schema-valid.

8. **Manifest and lineage binding are incomplete.** Ledger entries do not carry a
   manifest digest. The bootstrap verifies a manifest's self-declared hash, while
   `git_base.commit_hint` is explicitly informational and no trusted commit SHA is
   checked. A different manifest whose body and self-hash change together can pass the
   documented bootstrap check; the ledger gives no per-trial binding to detect it.

## Public schema acceptance vector

Using only dummy digests, Draft 2020-12 validation accepted a `completed` ledger row
with all of the following simultaneously:

```text
purpose_id = arbitrary-purpose
protected_gates = [not-a-manifest-gate]
lineage_parent = not-a-commit-or-id
metrics = {unrelated_proxy: 1.0}
evaluator_identity.digest = sha256:000...000
```

Changing that evaluator digest to `sha256:111...111` also validates. The vector has
one declared `display_selection` intervention and a required baseline control, which
shows that required-field presence does not establish evaluator pinning, a matched
control, purpose coverage, protected-gate coverage, or metric identity.

## Boundary conclusion

The v1 artifacts document the desired protections but do not enforce them at the
committed input boundary. Consequently, a hidden input, evaluator mutation,
purpose-free row, proxy metric, unmatched control, arbitrary lineage parent, or
incomplete gate set can be schema-valid and accepted unless a later executor adds
trusted cross-record validation. No valid trial should be unpaused on this input
contract alone.
