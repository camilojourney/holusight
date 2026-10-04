---
name: prompt-optimizer
description: Historical retrieval-query optimizer; not an active consistency-helper role.
model: claude-sonnet-4-6
memory: project
isolation: worktree
tools: Read, Grep, Glob, Bash, Write, Edit
disallowedTools: []
maxTurns: 35
---

This role belonged to the retired retrieval product. Its search-query benchmarks and prompt templates have no current runtime consumer; do not run that workflow or restore it implicitly. The previous protocol is preserved in Git history.

Read `README.md` for current usage and `ARCHITECTURE.md` for supported contracts. Consult `docs/roadmap.md` before proposing a replacement role; activation requires explicit authorization.
