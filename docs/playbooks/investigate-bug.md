# Playbook: Investigate a Bug

## 1. Reproduce

```bash
# Isolate to a fresh data dir to avoid cache interference
export HOLUSIGHT_DATA_DIR=/tmp/holusight-debug-$(date +%s)
python -m holusight index /path/to/test-docs
python -m holusight search "failing query" /path/to/test-docs
```

## 2. Check Logs

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python -m holusight search "query" /path/to/docs
```

## 3. Inspect State

For index corruption issues:
```python
import lancedb
db = lancedb.connect("~/.holusight/data/<folder-hash>/lance")
tbl = db.open_table("chunks")
print(tbl.count_rows())
```

For FTS issues:
```python
import sqlite3
conn = sqlite3.connect("~/.holusight/data/<folder-hash>/metadata.db")
print(conn.execute("SELECT count(*) FROM chunks_fts").fetchone())
```

## 4. Verify Read-Only Invariant

```bash
# Should find ZERO results — any write to folder_path is a bug
grep -rn "open.*'w'" src/holusight/
```

## 5. Write a Regression Test

Once fixed, add a test in `tests/` that reproduces the bug.
File name: `test_<module>_<bug_description>.py`
