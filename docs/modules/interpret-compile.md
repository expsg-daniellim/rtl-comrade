# `interpret-compile`

**Class:** `InterpretCompileMod` (`modules/rtl_buddy/build.py`)

[Back to index](index.md)

Reads the finished compile `Proc`. On `rc == 0` forwards test + `simv` to the sim stage; otherwise emits nothing and logs `compile_failed` at `ERROR`.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the test |
| `simv` | `str` | the sim binary path from [build-compile-cmd](build-compile-cmd.md) |
| `proc` | `Proc` | finished compile process from [run-process](run-process.md) |

## Outputs

`test` + `simv` — forwarded on success. A failed compile emits nothing.

## Failure routing

Compile failure is business logic, not an exception — it logs `compile_failed` at `ERROR`. The stderr tail (last 4 KiB) is attached to the log event when readable; an unreadable stderr file is tolerated (`OSError` swallowed).

## Graph node

`cc-int`, contract `keyed_join` (`key_field: key`, `unwrap: true`, `ignore: [test]`). The `simv` edge rides the wire as a `KeyedValue`; the contract unwraps it on the way in and rewraps the forwarded `simv` on the way out, so the module never handles the key.
