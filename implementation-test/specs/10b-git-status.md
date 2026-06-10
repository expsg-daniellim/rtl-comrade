# Spec 10b: git-status (`GitStatusMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Control section](../03-module-catalog.md),
[07 item 27](../07-ambiguities-and-assumptions.md). Parent index:
[10 — Control module, git-status, and the summary logging plugin](10-control-aggregate-modules.md).

## Goal

Record git state once as a structured log event for reproducibility (TODO #15 — a logging
concern, not a graph-routed payload).

## Deliverables

In `modules/rtl_test/setup.py` — `GitStatusMod`:

Zero-input `unit` node. `run(self)` shells out to git (`git rev-parse --abbrev-ref HEAD`,
`git rev-parse HEAD`, `git status --porcelain`) and calls
`log.info("git_state", branch=..., sha=..., dirty=bool(...))` once. If not in a git repo or
`git` is unavailable, `log.warning("git_state_unavailable", reason=...)` and emit nothing
collectable — **never** `log.error`/`log.critical`. Returns `("default", True)`; the port is
unwired (the node exists only for the side-effect log).

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:500-522` — `show_git_rev` (here emitted as one structured `git_state` event rather than printed).

Manifest entries for `GitStatusMod` per [06](../06-graph-yaml.md).

## Tests

`modules/tests/test_control.py`:

- `GitStatusMod` in a temp git repo emits `git_state` with branch/sha/dirty; outside a repo
  emits `git_state_unavailable` at WARNING and no ERROR/CRITICAL.

## Acceptance criteria

- Tests pass.
- In a git repo, emits one `git_state` event (branch/sha/dirty) at INFO; outside a repo,
  emits `git_state_unavailable` at WARNING and never `log.error`/`log.critical`.
