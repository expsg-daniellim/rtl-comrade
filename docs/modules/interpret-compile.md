# `interpret-compile`

**Class:** `InterpretCompileMod` (`modules/rtl_buddy/build.py`)

[Back to index](index.md)

Reads the finished compile `Proc`. On `rc == 0` forwards test + `simv` to the sim stage; otherwise emits a `compile_fail` result and logs the tail of stderr for diagnosis.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the test |
| `simv` | `str` | the sim binary path from [build-compile-cmd](build-compile-cmd.md) |
| `proc` | `Proc` | finished compile process from [run-process](run-process.md) |

## Outputs

`test` + `simv` — forwarded on success; `fail` — a `TestResult.compile_fail` on non-zero return.

## Failure routing

Compile failure is business logic, not an exception — it routes to `fail`. The stderr tail (last 4 KiB) is attached to the `compile_failed` `ERROR` log when readable; an unreadable stderr file is tolerated (`OSError` swallowed).

## Graph node

`cc-int`, contract `keyed_join` (`key_field: key`, `unwrap: true`, `ignore: [test, fail]`). The `simv` edge rides the wire as a `KeyedValue`; the contract unwraps it on the way in and rewraps the forwarded `simv` on the way out, so the module never handles the key. The `fail` port fans into [summarise-results](summarise-results.md) as `compile_fail`.
