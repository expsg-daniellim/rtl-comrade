# `route-post`

**Class:** `RoutePostMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Routes a run to the UVM parser or the plain parser depending on whether the test declares a `uvm` config.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run |
| `proc` | `Proc` | finished sim |

## Outputs

`uvm_test` + `uvm_proc` when `test.uvm is not None`; `plain_test` + `plain_proc` otherwise. Exactly one pair fires.

## Graph node

`route-post`, contract `keyed_join` (`key_field: key`). The UVM pair feeds [parse-uvm-log](parse-uvm-log.md); the plain pair feeds [parse-log](parse-log.md).
