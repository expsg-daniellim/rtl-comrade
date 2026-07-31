# Spec 01: FilelistEntry (datatype)

**Depends on:** [implementation-test spec 01](../implementation-test/specs/01-shared-schema.md) (`KeyedValue`, the envelope this rides inside).
**References:** [00-overview](00-overview.md#why-this-pipeline-exists); consumed by specs [02](02-filelist-extract.md)–[08](08-prioritised-merge.md).

## Before you start

Read `docs/modules/implementation.md`. This spec defines a shared datatype only — no node, no contract.

## Goal

Define `FilelistEntry`, the record for one entry in a filelist, replacing the positional `(path, option)` tuple threaded through the pipeline. A named record removes the `[0]`/`[1]` ambiguity and leaves room for entry-local metadata without disturbing the pipeline's shape.

## Definition

```python
@dataclass(frozen=True)
class FilelistEntry:
    path:str             # resolved/rewritten path; for a +libext+ entry, the coalesced value
    option:str|None      # option token: "-v ", "-y ", "+incdir+", "+libext+", or None
```

It lives in `modules/rtl_buddy/build.py` alongside the pipeline modules. It is a plain data type, not a plugin — no manifest entry.

## Fields

| field | meaning |
|---|---|
| `path` | the entry's path, resolved by `filelist-extract` and rebased by `filelist-normalise`; for a `+libext+` entry it holds the coalesced extension value, not a path |
| `option` | the parsed option prefix — `-v `, `-y `, `+incdir+`, `+libext+`, or `None` for a bare source file |

Future metadata (originating source, source line, …) can be added as further fields without touching the transforms, since each reads only the fields it needs.

## The key is not a field

The correlation key (`test.key`) is deliberately **not** a `FilelistEntry` field. The key identifies the whole filelist — one per test — not an individual line, and `keyed_join` reads it from the payload *envelope*, not from list elements. Entries therefore travel as `KeyedValue[list[FilelistEntry]]`: the key on the `KeyedValue`, the entries in its `.value`. Putting a key on each entry would be redundant *and* would not satisfy `keyed_join` — a bare `list` has no `.key`.

Keeping the key on the envelope is also what lets the `keyed_join` nodes ([07](07-write-filelist.md), [08](08-prioritised-merge.md)) run `unwrap: true`: the contract unwraps a payload only when a `value` sits beside the key, so those modules take and return a plain `list[FilelistEntry]` and the envelope stays entirely the contract's business.

## Deliverables

- `FilelistEntry` dataclass in `modules/rtl_buddy/build.py`.
- No manifest entry (it is a type, not a module or contract).

## Constraints

- Frozen dataclass — entries are values, compared field-wise for dedup (spec [06](06-filelist-dedup.md)).
- **No `key` field** — the key rides on the `KeyedValue` envelope (see above).
- `+libext+` entries keep the coalesced value in `path`, with `option == "+libext+"`.

## Note — migration

Specs [02](02-filelist-extract.md)–[08](08-prioritised-merge.md) still describe entries as `list[tuple[str, str | None]]`. Migrating those signatures to `list[FilelistEntry]` (`.path`/`.option` access) is folded into the payload/key-threading rework and is not yet reflected in those specs.
