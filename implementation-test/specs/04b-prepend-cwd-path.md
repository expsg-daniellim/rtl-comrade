# Spec 04b: prepend-cwd-path (`PrependCwdPathMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md),
[07 settled 25](../07-ambiguities-and-assumptions.md). Parent index:
[04 — Setup modules](04-setup-modules.md). Sequencing consumer:
[spec 03 — run-process](03-run-process.md) (`env_ready`).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, shared with the setup chain
(`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain (`05a`–`05f`,
index [05](05-selection-expansion-modules.md)), and git-status (`10b`); coordinate shared
imports and helpers with those specs.

## Goal

Prepend `.` to `os.environ["PATH"]` so a CWD-local simulator is discoverable by subsequent
subprocess invocations, sequenced ahead of every `run-process` call via `env_ready`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   —  (zero-input; runs once)
outputs:  default → bool   (always True; receiver uses it only for sequencing)
```

```python
class PrependCwdPathMod:
    def run(self):
        parts = os.environ.get("PATH", "").split(os.pathsep)
        if "." not in parts:
            os.environ["PATH"] = os.pathsep.join(["."] + parts)
        return ("default", True)
```

## Deliverables

In `modules/rtl_test/setup.py`:

- `PrependCwdPathMod` — prepends `.` to `os.environ["PATH"]` so a CWD-local simulator
  (`simv`, `verilator`) is discoverable by subsequent subprocess invocations. Mirrors
  `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102`, which does the same once at CLI
  bootstrap; here it is an explicit graph node so the responsibility is visible. Zero
  input ports; runs once via `unit`. Emits `True` on `default`; the value is consumed by
  `run-process` as a `env_ready` sequencing input (see [07 settled
  25](../07-ambiguities-and-assumptions.md)).
  **Behaviour**:
  1. `path = os.environ.get("PATH", "")`
  2. If `"." not in path.split(os.pathsep)`: `os.environ["PATH"] = "." + os.pathsep + path`.
  3. Return `{"default": True}`.
  Idempotent — re-invocation (or a stale `.` already on PATH) is a no-op. Mutation of
  the process-wide `os.environ` is safe because `unit` guarantees a single invocation.
  **Failure handling**: none. Dict mutation cannot meaningfully fail; no failure port,
  no log call.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102` — the `PATH` prepend in `RtlBuddy.__init__`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: prepend-cwd-path, class_name: PrependCwdPathMod }
```

## Tests

In `modules/tests/test_setup.py`:

- With a `PATH` that does not contain `.`, `run()` mutates `os.environ["PATH"]` to start
  with `. + os.pathsep` and returns `{"default": True}`.
- With a `PATH` that already starts with `.`, `run()` leaves it unchanged and still
  returns `{"default": True}` (idempotent).
- With a `PATH` that contains `.` somewhere in the middle, `run()` leaves it unchanged
  (not just the head position counts).
- End-to-end with `run-process` — after `PrependCwdPathMod.run()` fires, a
  `RunProcessMod.run()` call with `argv=["./local_tool"]` (a script written into the temp
  CWD with the exec bit set) resolves and executes the binary, where the same call would
  fail with `FileNotFoundError` if the prepend had not happened. Restore
  `os.environ["PATH"]` in the test fixture teardown.

## Acceptance criteria

- Tests pass.
- `PrependCwdPathMod` leaves `os.environ["PATH"]` starting with `.` for the duration of the
  run (contributes to the setup-only end-to-end graph — see
  [04 index](04-setup-modules.md#acceptance-criteria)).
