# AVO Mini Bootstrap v1

**Campaign:** `holusight-avo-v1`  
**Role:** The Mini is the **global supervisor** for all AVO lanes.

## Prerequisites

- Git remote `origin` reachable.
- Branch `fm/holusight-avo-setup-v1` pushed with verified manifest.
- No credentials, hidden holdout payloads, or G2 branch checkout required for bootstrap.

## Exact bootstrap command

Run on the Mini host from a clean Holusight worktree based on `origin/master`:

```bash
git fetch origin fm/holusight-avo-setup-v1 && \
MANIFEST_PATH='docs/avo/trial-manifest.v1.json' && \
git show "origin/fm/holusight-avo-setup-v1:${MANIFEST_PATH}" > /tmp/avo-trial-manifest.v1.json && \
python3 - <<'PY'
import hashlib, json, pathlib, sys

path = pathlib.Path("/tmp/avo-trial-manifest.v1.json")
data = json.loads(path.read_text())
expected = data.get("manifest_sha256")
if not expected or not expected.startswith("sha256:"):
    sys.exit("missing manifest_sha256")
body = {k: v for k, v in data.items() if k != "manifest_sha256"}
computed = "sha256:" + hashlib.sha256(
    json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
if expected != computed:
    sys.exit(f"manifest hash mismatch: expected {expected}, got {computed}")
if data.get("supervisor", {}).get("role") != "global_supervisor":
    sys.exit("Mini supervisor role not declared")
if data.get("schema_version") != "holusight-avo-trial-manifest/v1":
    sys.exit("unsupported schema_version")
print("AVO manifest verified:", data["campaign_id"], "sha256=", expected)
PY
```

Expected success output (hash will match committed manifest):

```text
AVO manifest verified: holusight-avo-v1 sha256= sha256:<64-hex>
```

## Post-bootstrap supervisor duties

1. **Verify** every laptop lane's first checkpoint carries the same `manifest_sha256`.
2. **Register** lane branches in the manifest `lane_registry` before accepting checkpoints
   (or reject checkpoints from unregistered branches).
3. **Own** experiment IDs `0501`–`1000` exclusively; never assign laptop IDs to Mini trials.
4. **Veto** trials that violate protected gates; record `supervisor_veto` rejections.
5. **Declare** `campaign_pause` or `lane_close` when resource, custody, or conflict
   conditions require laptop lanes to stop.
6. **Never** merge lane branches, promote artifacts, or modify G2 code.

## Supervisor checkpoint location

Mini supervisor state (counts, vetoes, pause flags) is published only on a registered
Mini lane branch under:

```text
docs/avo/lanes/mini-supervisor/checkpoints/
```

using schema `holusight-avo-checkpoint/v1`, subject to the same leakage boundary as
laptop lanes.

## Laptop lane handoff

Laptop lanes must not start valid trials until this bootstrap command succeeds on the
Mini and the setup-branch manifest is available at
`origin/fm/holusight-avo-setup-v1:docs/avo/trial-manifest.v1.json`.

## Non-goals

- This bootstrap does not run trials, open network clients beyond `git fetch`, or
  access hidden holdout content.
- This bootstrap does not authorize merge or promotion.
