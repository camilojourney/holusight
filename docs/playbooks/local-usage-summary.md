# Local usage summary

`holus usage-summary --format json` reads the existing local `events.jsonl` event
source and emits a deterministic aggregate. Events contain only command metadata,
a short hash of the project identity, an optional bounded agent identifier, provider
state, measured latency/token fields, and aggregate feedback signals. Prompts,
source, audio, credentials, and paths are never persisted. No network access or
fixture promotion is performed.

`HOLUSIGHT_LOCAL_TRACE=0` disables writes. A project can opt out with
`.holusight/local-usage.disabled` (the marker is local project configuration and is
not read from indexed content). Missing events produce zero counts. A provider is
reported as `not_used` only when its status was present but it was not invoked;
missing providers are not inferred. Provider `current`, `partial`, `stale`,
`unavailable`, and `unknown` remain distinct. Latency and token totals are
`unknown` unless the event supplied measured values. Feedback totals are aggregate
`failure_case` and `aggregate_outcome` signals only.

The summary is advisory evidence for prioritizing retrieval improvements. It does
not claim adoption, alter canonical fixtures, or transmit data. `project_id` and
`agent_id` counts describe invocations observed in this local event file; unknown
agent identity is explicit rather than guessed.
