# Spec 15: SimCommandBuild

## What this covers

Implement `SimCommandBuild` in `modules/rtl_buddy_compat/sim.py` (the file created by spec 13). This module constructs the simulator command argv and resolves the log path prefix and timeout. No subprocess is run here — that is spec 16.

## Prerequisites

Specs 00 and 13 (artefacts + sim.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L73-L86` — simulator executable and log path
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L95-L119` — plusargs and plusdefines construction
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L247-L263` — runtime command construction
- `rtl_buddy/src/rtl_buddy/config/rtl.py:L60-L80` — `get_run_time_opts(mode, seed)`, `get_exe()`
- `rtl_buddy/src/rtl_buddy/config/test.py:L171-L189` — `get_timeout()` logic

## Addition to `modules/rtl_buddy_compat/sim.py`

### `SimCommandBuild`

```
contract: latest, trigger_ports: [resolved]
inputs:  resolved: ResolvedRunPlan, root: RootContext
outputs: default → SimCommand
```

Implementation steps:

1. Reconstruct builder config from `root.rtl_builder_cfg`.
2. Determine simulator executable:
   - If builder type is Verilator: `<build_dir>/simv`
   - Otherwise: configured `simv` path from builder config
3. Build `argv`:
   - `[sim_exe]`
   - `+ get_run_time_opts(root.rtl_builder_mode, resolved.seed)` (`rtl.py:L60-L80`)
   - `+ [f"+define+{k}" if v is None else f"+define+{k}={v}" for k, v in resolved.test.plusdefines.items()]`
   - `+ plusarg_strings` where each plusarg is formatted as `+arg` or `+arg=val`
4. Determine `log_path_prefix`:
   - `run_id=None` → `<build_dir>/test`
   - `run_id=N` → `<build_dir>/test_<N:04d>`
5. Determine timeout: `resolved.test.timeout or builder_default_timeout or 3600`.
6. Emit `SimCommand(argv=argv, cwd=root.project_root, key=resolved.key, log_path_prefix=log_path_prefix, timeout_seconds=timeout, seed=resolved.seed, test=resolved.test)`.

Compatibility: `vlog_sim.py:L73-L86, L95-L119, L247-L263`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `sim.py` entry:

```yaml
  - name: sim_command_build
    class_name: SimCommandBuild
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_sim_command_build.py`.

- `run_id=None` → `log_path_prefix` ends with `/test`
- `run_id=3` → `log_path_prefix` ends with `/test_0003`
- `plusargs=["verbose"]` → `"+verbose"` in argv
- `plusargs=[{"timeout": "100"}]` → `"+timeout=100"` in argv
- `plusdefines={"DEBUG": None}` → `"+define+DEBUG"` in argv
- `plusdefines={"WIDTH": "8"}` → `"+define+WIDTH=8"` in argv
- `resolved.test.timeout=60` → `timeout_seconds=60`
- `resolved.test.timeout=None` → uses builder default or sentinel

## Constraints

- Must not run any subprocess.
- Plusarg format: `+key` for bare args, `+key=value` for keyed args. Check `vlog_sim.py:L95-L107` for the exact format.
- `run_id=3` formats as `_0003` (four-digit zero-padded).
