# `run-process`

**Class:** `RunProcessMod` (`modules/rtl_buddy/build.py`)

[Back to index](index.md)

The reusable subprocess star. Launches a `Command`'s `argv` in its own process group, redirects stdout/stderr to the command's log files, waits (optionally with a timeout), and emits a `Proc` describing the outcome. Used twice in the `test` graph — once for compile (`cc-run`), once for sim (`sim-run`).

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `command` | `Command` | — | the subprocess to run (`argv` + log paths + key) |
| `work_dir` | `Path` | — | subprocess `cwd` |
| `timeout` | `float \| None` | `None` | wall-clock limit; `None` means wait indefinitely |
| `env_ready` | `bool` | `True` | gate token from [prepend-cwd-path](prepend-cwd-path.md) ensuring `$PATH` is set before any launch |

## Config

```yaml
config:
  grace_s: 5.0
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `grace_s` | `float` | `5.0` | seconds to wait after `SIGQUIT` before escalating to `SIGKILL` |

## Outputs

`default` — a `Proc(key, rc, stdout_path, stderr_path)`. `rc` is the process return code, or `None` when the process was killed on timeout.

## Behaviour

- The child is started with `preexec_fn=os.setpgrp` so the whole process group can be signalled together.
- On timeout: `SIGQUIT` the group, wait up to `grace_s`, then `SIGKILL` if still alive; the emitted `Proc` carries `rc=None` (interpreted downstream as a timeout).
- On harness cancellation (`asyncio.CancelledError`): the same SIGQUIT→grace→SIGKILL cleanup runs under `asyncio.shield`, then the `CancelledError` is **re-raised** so the harness can cancel the node cleanly — the one exception a module lets propagate.

## Failure routing

A missing or non-executable binary (`FileNotFoundError`, `PermissionError` at launch) is `log.fatal` (`launch_failed`) — the flow cannot proceed. `ProcessLookupError` during signalling is swallowed (the process already exited).

## Graph node

`cc-run` (contract `default`, `persistent_inputs: [env_ready, work_dir]`) and `sim-run` (contract `keyed_join`, `key_field: key`, `persistent_inputs: [env_ready, work_dir]`, `unwrap: true`, `ignore: [default]`, `config: { grace_s: 5.0 }`). `sim-run`'s `timeout` edge rides the wire as a `KeyedValue` and is unwrapped by the contract; the emitted `Proc` keys itself off the `Command`, so `default` is left untouched. `cc-run` has no `timeout` edge, so the Python default applies there.
