# Spec 10b: git-status (`GitStatusMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Control section](../03-module-catalog.md),
[07 item 27](../07-ambiguities-and-assumptions.md). Parent index:
[10 — Control module, git-status, and the summary logging plugin](10-control-aggregate-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

## Goal

Record git state once as a structured log event for reproducibility — a logging
concern, not a graph-routed payload.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   —  (zero-input; runs once)
outputs:  default → bool   (always True; unwired — node exists for its log.info side-effect)
```

```python
class GitStatusMod:
    def run(self):
        try:
            branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.strip())
            log.info("git_state", branch=branch, sha=sha, dirty=dirty)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.warning("git_state_unavailable", reason=str(e))   # never error/critical
        return ("default", True)
```

## Algorithm

1. Collect git state via three `subprocess.run(..., capture_output=True, text=True,
   check=True)` calls: `branch` from `git rev-parse --abbrev-ref HEAD`, `sha` from `git
   rev-parse HEAD`, and `dirty = bool(... "git status --porcelain" ...stdout.strip())`.
2. Record it once: `log.info("git_state", branch=branch, sha=sha, dirty=dirty)`. The event is
   not collected by `SummaryProcessor` (results-only), so it falls through to the console and
   prints at run start.
3. Emit `("default", True)` — the port is unwired; the node exists only for the side-effect
   log.
4. **Failure — not a repo / git absent.** Wrap step 1 in `try/except (CalledProcessError,
   FileNotFoundError)` → `log.warning("git_state_unavailable", reason=str(e))`. **Never**
   `log.error`/`log.fatal`: missing git state must not fail the run. Step 3 still emits.

## Deliverables

In `modules/rtl_buddy/setup.py` — `GitStatusMod`:

Zero-input `unit` node. `run(self)` shells out to git (`git rev-parse --abbrev-ref HEAD`,
`git rev-parse HEAD`, `git status --porcelain`) and calls
`log.info("git_state", branch=..., sha=..., dirty=bool(...))` once. The `git_state` event is
not collected by any plugin — it falls through the `SummaryProcessor` (which accumulates
results only) to the console and prints at run start. If not in a git repo or `git` is
unavailable, `log.warning("git_state_unavailable", reason=...)` — **never**
`log.error`/`log.fatal`. Returns `("default", True)`; the port is unwired (the node exists
only for the side-effect log).

**Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:500-522` — `show_git_rev` (here emitted as one structured `git_state` event rather than printed).

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: git-status, class_name: GitStatusMod }
```

## Tests

`modules/tests/test_control.py`. Fixtures: `tmp_path` initialised as a git repo (shell `git
init` + a commit) via `monkeypatch.chdir`; `logging_handler` to inspect emitted events and
assert `failure is False` throughout.

- Clean git repo → emits `("default", True)` and one `log.info("git_state", branch=…, sha=…,
  dirty=False)`; no WARNING/ERROR.
- Git repo with an uncommitted change → `git_state` event with `dirty=True` (boundary: dirty
  flag from `git status --porcelain`).
- CWD outside any git repo (`git rev-parse` exits non-zero) → `CalledProcessError` caught →
  emits `("default", True)` and `log.warning("git_state_unavailable", …)`; **no**
  ERROR/CRITICAL, `logging_handler.failure is False`.
- `git` binary unavailable (monkeypatch `subprocess.run` to raise `FileNotFoundError`) → caught
  → emits `("default", True)` and `log.warning("git_state_unavailable", …)`; no ERROR/CRITICAL
  (boundary: tool missing must not fail the run).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised (emits `True`, sequencing only): in a git repo it emits one
  `git_state` event (branch/sha/dirty) at INFO; outside a repo it emits
  `git_state_unavailable` at WARNING and never `log.error`/`log.fatal`.
- The `modules/config.yaml` manifest entry `{ name: git-status, class_name: GitStatusMod }`
  validates and the harness resolves `git-status` → `GitStatusMod`.

## Constraints

- `unit` contract, zero-input — runs once for its `log.info("git_state", …)` side-effect.
- Catch `(subprocess.CalledProcessError, FileNotFoundError)` (not a repo / `git` absent) →
  `log.warning("git_state_unavailable", …)`. **Never** `log.error`/`log.fatal` — missing git
  state must not fail or abort the run.
- `git_state` is **not** collected by `SummaryProcessor` (results-only); it falls through to the
  console at run start.
- Emit `("default", True)` — the port is unwired; the node exists only for the log side-effect.
