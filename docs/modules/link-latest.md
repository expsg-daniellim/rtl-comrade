# `link-latest`

**Class:** `LinkLatestMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Atomically repoints the `test.log`, `test.err`, and `test.randseed` symlinks in the working directory at this run's outputs, so the newest run is always reachable by a stable name. Pure side effect; emits nothing.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `randseed` | `RandSeed` | supplies the `.randseed` target |
| `proc` | `Proc` | supplies the `.log`/`.err` targets |
| `randseed_done` | `RandSeedDone` | ordering gate; ensures [write-randseed](write-randseed.md) ran first (unread) |
| `work_dir` | `Path` | where the symlinks live |

## Outputs

None.

## Behaviour

`force_symlink` (module-level helper) creates a temp link and atomically `os.replace`s it over any existing link.

## Graph node

`link-latest`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [work_dir]`).
