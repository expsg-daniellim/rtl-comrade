# `prepend-cwd-path`

**Class:** `PrependCwdPathMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Prepends `.` to `$PATH` (if absent) so builder/sim binaries in the working directory resolve. Emits a token used purely to gate the two [run-process](run-process.md) nodes — its `True` value means "environment is ready", wired to their `env_ready` port.

## Inputs

None — source node.

## Outputs

`default` — `True` (a readiness token).

## Graph node

`prepend-path`, contract `default`. Its output feeds `cc-run.env_ready` and `sim-run.env_ready` as a required edge.
