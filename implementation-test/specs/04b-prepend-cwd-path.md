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
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

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

## Algorithm

1. Read the current value: `path = os.environ.get("PATH", "")`.
2. If `"." not in path.split(os.pathsep)`, prepend it: `os.environ["PATH"] = "." + os.pathsep
   + path`. If `.` is already present anywhere in the list, leave `PATH` untouched
   (idempotent).
3. Emit `("default", True)` — a sequencing token only; receivers branch on ordering, not on
   the boolean.

No failure path: dict mutation cannot meaningfully fail, and `unit` guarantees the single
invocation that makes the process-wide `os.environ` mutation safe.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `PrependCwdPathMod` — prepends `.` to `os.environ["PATH"]` so a CWD-local simulator
  (`simv`, `verilator`) is discoverable by subsequent subprocess invocations. Mirrors
  `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102`, which does the same once at CLI
  bootstrap; here it is an explicit graph node so the responsibility is visible. Zero
  input ports; runs once via `unit`. Emits `True` on `default`; the graph wires it to each
  `run-process`'s `env_ready` port, with the edge marked
  **`required: true`** and `env_ready` in the consumer's `persistent_inputs` — so the first
  subprocess blocks until the PATH mutation is done (hard ordering) and the once-emitted token is
  replayed on later invocations (see [07 settled 25](../07-ambiguities-and-assumptions.md)). See
  [Algorithm](#algorithm) for the numbered steps.
  **Failure handling**: none. Dict mutation cannot meaningfully fail; no failure port,
  no log call.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102` — the `PATH` prepend in `RtlBuddy.__init__`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: prepend-cwd-path, class_name: PrependCwdPathMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `monkeypatch.setenv("PATH", …)` to control the
starting value (auto-restored on teardown); `tmp_path` + exec-bit script for the end-to-end
case.

- `PATH` without `.` (e.g. `"/usr/bin:/bin"`) → emits `("default", True)` and
  `os.environ["PATH"]` becomes `"." + os.pathsep + "/usr/bin:/bin"`.
- `PATH` already starting with `.` → emits `("default", True)` and `PATH` is unchanged
  (idempotent at the head).
- `PATH` with `.` somewhere in the middle (e.g. `"/usr/bin:.:/bin"`) → emits
  `("default", True)` and `PATH` unchanged (any position counts, not just the head).
- `PATH` unset entirely (`monkeypatch.delenv("PATH")`) → `os.environ.get("PATH", "")` yields
  `""` → emits `("default", True)` and `PATH` becomes `"."` (boundary: missing var).
- End-to-end with `run-process` — after `PrependCwdPathMod.run()` fires, a `RunProcessMod`
  call with `argv=["local_tool"]` (a script written into the `tmp_path` CWD with the exec bit
  set) resolves and executes the binary, where the same call before the prepend raises
  `FileNotFoundError`.

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: emits `True` and leaves `os.environ["PATH"]` starting
  with `.` for the duration of the run (contributes to the setup-only end-to-end graph —
  see [04 index](04-setup-modules.md#acceptance-criteria)).
- No failure path: the module always emits and never logs an error.
- The `modules/config.yaml` manifest entry `{ name: prepend-cwd-path, class_name: PrependCwdPathMod }`
  validates and the harness resolves `prepend-cwd-path` → `PrependCwdPathMod`.

## Constraints

- `unit` contract, zero-input — runs exactly once; the single invocation is what makes the
  process-wide `os.environ["PATH"]` mutation safe. Do **not** wire it for repeated execution.
- Idempotent: prepend `.` only if it is **not already present anywhere** in the split `PATH`;
  otherwise leave `PATH` untouched.
- No failure path — dict mutation cannot meaningfully fail; no failure port, no log call.
- Emit `("default", True)` as a sequencing token only; the boolean is never branched on — the
  consuming `run-process` uses it purely for edge ordering.
