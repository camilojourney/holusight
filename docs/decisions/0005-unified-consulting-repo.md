# 0005 — Unified Consulting Repo into Holusight

**Date:** 2026-03-03
**Status:** Accepted

## Context

The consulting business (`camilo-martinez-consulting`) was a separate Type D (spec-only) repo with zero code. It existed solely to house business operations — proposals, pipeline, playbooks, market analysis — for selling Holusight as a consulting engagement.

Having two repos created overhead: two sets of docs/, decisions/, CLAUDE.md, agents, all for one business unit. The consulting repo was 100% dependent on holusight.

## Decision

Merge all consulting business content into `holusight/business/`. Move consulting agents (proposal-writer, business-analyst, market-expert, delivery-planner) into holusight's `.claude/agents/` with updated paths. Archive the consulting repo.

## Consequences

- One repo to manage instead of two
- Business strategy lives next to technical implementation
- Agents can reference both code and business docs without cross-repo lookups
- Fleet drops from 11 to 10 repos
- The `camilo-martinez-consulting` repo can be archived on GitHub
