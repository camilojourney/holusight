# Holusight

Holusight is a local-first repository-evidence tool for agents. It answers questions about a project with bounded exact, structural, consistency, and optional semantic evidence, while reporting provenance, freshness, and whether an evidence provider is unavailable. It does not turn a partial result into a successful answer. The project website is [holusight.com](https://holusight.com/); this README makes no claim about that site's product behavior.

## Install anywhere

Install the CLI globally, then bootstrap the skill in each project that uses it. The skill bootstrap is project-local and missing-only: it writes only `.agents/skills/holusight/` and preserves an existing project copy. It does not require or create a machine-wide skill directory. Requires [`uv`](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/camilojourney/holusight
cd ~/some/project
holusight-install-skill --project-local
```

`holus`, `holusight-install-skill`, and the other `[project.scripts]` entries land on your `PATH` (`uv tool install` puts them in `~/.local/bin` - make sure that's on `PATH`). From then on, invoke `/holusight` inside that project.

For a checkout or installed CLI:

```bash
holusight-install-skill --project-local
```

The project-local destination is validated against the current project root and symlink escapes are rejected.

## Repository evidence

```bash
cd ~/some/project
holus                                      # repository snapshot and provider health
holus evidence "where is retry policy enforced?"
holus evidence "how does X work?" --mode structure
holus providers                            # availability and freshness
```

Exact, structural, and consistency evidence work without an embedding index. Structural evidence consumes `graphify-out/graph.json`; when it is missing or older than HEAD, Holusight invokes the installed `graphify` executable with `update .` and then reads the result. Its citation is marked current only when the graph's `built_at_commit` matches repository HEAD. A missing graph or failed builder is unavailable, and an unreadable or stale result is never presented as current. Builder discovery uses `PATH`, not a machine-specific script path.

Semantic evidence requires an explicit index build:

```bash
python -m holusight index .
holus evidence "how does X work?" --mode semantic
```

A missing, incomplete, or stale embedding index is a failure, not a successful partial answer. Exact matches cannot mask unavailable semantic evidence. Queries are local by default; external embedding access requires an explicit egress opt-in.

## Project-local skill controls

```bash
holusight-install-skill --print       # preview without writing
uv tool install --editable .          # develop from a local checkout
uv tool install --upgrade git+https://github.com/camilojourney/holusight
uv tool uninstall holusight
```

The installed skill records its interpreter in project-local derived state when needed. Holusight's search data is kept outside the indexed folder, keyed by that folder's path, and is never written into the repository being searched.

## Evidence contract

Every provider reports an explicit state such as `ok`, `no_evidence`, `unavailable`, `stale`, or `budget_exceeded`. Evidence items include their source and location, and available providers attach provenance and freshness. If the required provider is unavailable or stale, the command exits nonzero and reports that state instead of presenting a partial answer as authoritative.

No public hosting or deployment behavior is implied by this repository README. The supported product surface described here is the local CLI and its project-local skill.

See [ARCHITECTURE.md](ARCHITECTURE.md) and the numbered specifications in [specs/](specs/) for implementation detail.
