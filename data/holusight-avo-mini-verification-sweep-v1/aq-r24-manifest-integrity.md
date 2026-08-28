# AQ-R24 / AVO input-integrity review — 2026-08-28

## Scope and immutable inputs

This is a read-only Mini review. It inspected only Git objects already visible in
this worktree; it did not fetch, read hidden inputs, alter G2, create a
trial/evaluator substitute, run a trial, or count a result.

| Input | Immutable identity |
|---|---|
| Canonical setup commit | `5679a8ba2e1288e14a3b01907699b467756c933c` (`origin/fm/holusight-avo-setup-v1`) |
| Canonical tree | `9ee027d00a47b363710572520d39cafa688b3026` |
| Published Mini remediation contract | commit `f5b5ddfde08ba16e87397f0b6fc07f8ea4174078`, `data/holusight-avo-mini-remediation-review-v1/report.md`, blob `79ab69199ea6585b9579880fc684b4a69d8f2443`, SHA-256 `87618adda0e5565f3cfcd1d331b26557da88c2ea706479ec190c0593a3ea8bf3` |

The remediation contract requires a reviewed correction before **any** valid
trial, including visible immutable content-bound AQ-R24, final G2 implementation
and pin, manifest, evaluator identity, matched control, and validated required
hashes. It further requires launch to remain denied pending independent laptop
and Mini review.

## Evidence and result

| Required item | Visible canonical evidence | Content-bound? | Result |
|---|---|---:|---|
| AQ-R24 | No `AQ-R24` occurrence in the canonical tree. | No | **FAIL** |
| Final G2 implementation and pin | `src/codesight/eval_suite.py` blob `5821324568c24d1ff5ae8cc4e6611efc803b7ad8` (SHA-256 `0bcb17d8d1d81cea2c8c7623a7d7bb76cf7aec01650b16be73b5161f075274a9`) defines `EvaluatorPin` as `blocked_until_g2_trusted_sandbox` or `pinned`; the visible slice states readiness is false until a trusted G2 sandbox supplies a real pin. No pinned subject/digest instance or final implementation identity is published. | No final pin exists | **FAIL** |
| Canonical manifest | `docs/avo/trial-manifest.v1.json`: blob `f43079deb8803aa1dee65a419ca23d5331545adf`; raw-byte SHA-256 `afe42148acfe6beebafcf47d5db26493b01b0dda4d4dd7ed966cfc426429efda`. Its declared canonical-JSON self-hash is `sha256:28a9f0b69d0c61cf3f223bf13e4412efa11afc8cd90f85fb7cacd2e731f4b876`, which recomputes correctly. | Partially: self-consistent, but `git_base.commit_hint` is not an exact commit/tree/blob pin. | **INSUFFICIENT** |
| Canonical evaluator identity | The manifest lists identity categories and the ledger schema requires format-shaped `evaluator_identity.digest` and `method_config_sha256`; neither supplies an expected evaluator value or binds it to a canonical object. | No | **FAIL** |
| Matched-control binding | The ledger schema (blob `858e60108d312f9b0e93800603513c95113dc821`, SHA-256 `b929fde7dfdb1edb9105cf267498c9cdbef04414e07f391f87ce37038a95cae6`) requires a `control.kind` and digest, but has no `matched_control` field or rule that ties the digest to a candidate, parent, evaluator, manifest, corpus, or trial. The canonical tree contains no `matched control` or `matched_control` term. | No | **FAIL** |
| Required hash validation and countability | The trial-manifest schema (blob `255c566fe800ae540a4ce528ca4d11f30d6e55df`, SHA-256 `a097543d02e7cd42095f4e4aed2a868559e91556aafabbf1f776780646383bdf`) and checkpoint schema (blob `6985cdf8204286a1019772740c3f0dac94124d56`, SHA-256 `eea9837af7c403f6e73c39c343d3dfee7cc5ca486674a72d6094af0b08627336`) constrain hash syntax. They do not provide canonical evaluator/control values or a visible enforcement path that makes a result non-countable after validating all required bindings. | Manifest self-hash only | **FAIL** |

The canonical AVO documents explicitly preserve G2 isolation and say execution is
blocked. That is compatible with keeping G2 untouched, but it is not the final,
pinned implementation demanded by the remediation contract.

## Negative-case review vector

This vector is declarative only; it does not construct substitute inputs.

| Case | Required fail-closed behavior | Visible status |
|---|---|---|
| Absent manifest hash | Reject before a valid trial. | Mini bootstrap checks absence; **covered**. |
| Malformed manifest hash | Reject before a valid trial. | Mini bootstrap requires `sha256:`; schema requires 64 lowercase hex; **covered**. |
| Manifest hash mismatch | Reject before a valid trial. | Bootstrap recomputes the canonical-JSON self-hash; **covered**. |
| Manifest/ref substitution | Reject a self-consistent manifest retrieved after `origin/fm/holusight-avo-setup-v1` moves. | Bootstrap fetches the moving ref and verifies only the fetched document's self-hash; `commit_hint` is informational. No expected commit/tree/blob is compared; **not covered**. |
| Absent, malformed, or mismatched evaluator identity | Reject as non-countable against a published canonical evaluator pin. | Shapes are required in the ledger schema, but no canonical expected identity/pin exists and no visible verifier compares one; **not covered**. |
| Absent or malformed control | Reject before a valid trial. | `control` and its digest format are schema-required; **shape covered**. |
| Mismatched/substituted control | Reject unless the control is demonstrably matched to the exact candidate, parent, evaluator, and frozen inputs. | No matching relation or expected digest is defined; **not covered**. |
| Missing ledger/checkpoint/hash validation | Reject and do not count a result. | Schemas describe fields, but no visible countability enforcement binds and validates all required values; **not covered**. |

## Local checks

- Confirmed the exact canonical commit is locally addressable and that its remote
  ref names that object.
- Recomputed the manifest's documented canonical-JSON self-hash: match.
- Searched the canonical tree for `AQ-R24`, `matched control`,
  `matched_control`, and `final G2 evaluator`: no occurrences.
- Ran `uv run --extra dev pytest tests/test_eval_suite.py -q`: **15 passed**.
  These existing tests confirm the current G2 block model; they do not establish
  the remediation contract's missing inputs or bindings.

## Determination

**NO-GO — valid trials remain paused and no result is countable.** The visible
canonical input is a Git-only AVO scaffold, not the reviewed corrective commit
required by the published Mini remediation contract. A fresh independent review
is required only after a new exact committed correction publishes all failed
bindings and their fail-closed validators. No launch, promotion, merge, or G2
change is authorized by this report.
