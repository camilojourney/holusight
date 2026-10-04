---
name: model-quality-auditor
description: Historical embedding auditor; not an active consistency-helper role.
model: claude-sonnet-4-6
memory: project
isolation: worktree
tools: Read, Grep, Glob, Bash, Write, Edit
disallowedTools: []
maxTurns: 35
---

This role belonged to the retired embedding/retrieval product. There is no current model configuration or retrieval benchmark to audit; do not download models or run the retired workflow. The previous protocol is preserved in Git history.

Read `README.md` for current usage and `ARCHITECTURE.md` for supported contracts. Consult `docs/roadmap.md` before proposing a replacement role; activation requires explicit authorization.
