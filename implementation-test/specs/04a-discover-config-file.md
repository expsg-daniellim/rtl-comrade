# Spec 04a: discover-config-file (`DiscoverConfigFileMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module **creates** `modules/rtl_test/setup.py` — it is the first spec to write the
file, so establish the shared imports and module-level helpers here. The file then receives
further additions from the rest of the setup chain (`04b`–`04i`, index
[04](04-setup-modules.md)), the selection/expansion chain (`05a`–`05f`, index
[05](05-selection-expansion-modules.md)), and git-status (`10b`); coordinate shared imports
and helpers with those specs.

## Goal

Implement the run-once tree-walk that locates a named config file by walking up from CWD —
the entry point of the setup chain.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
config:   filename:str, max_levels:int = 8
inputs:   —  (zero-input; runs once)
outputs:  default → Path
```

```python
class DiscoverConfigFileMod:
    @serde
    class Config:
        filename:str
        max_levels:int = 8

    def __init__(self, config):
        self.filename = config.filename
        self.max_levels = config.max_levels

    def run(self):
        d = Path.cwd()
        for _ in range(self.max_levels):
            if (d / self.filename).is_file():
                return ("default", d / self.filename)
            if (d / ".git").exists() or d == d.parent:
                break
            d = d.parent
        log.critical("config_not_found", filename=self.filename)
```

## Algorithm

1. Seed the walk at the current directory: `d = Path.cwd()`.
2. Loop at most `self.max_levels` times. If `(d / self.filename).is_file()`, the file is
   found — emit `("default", d / self.filename)` and return.
3. Stop climbing at a boundary: if `(d / ".git").exists()` (git root) or `d == d.parent`
   (filesystem root), break. Otherwise ascend (`d = d.parent`) and repeat step 2.
4. **Failure — not found.** Falling out of the loop (depth limit hit, or a boundary reached
   with no match) is the not-found case: `log.critical(f"{self.filename} not found walking up
   from CWD")` (harness exits 1). A `PermissionError` raised while listing a directory is not
   caught — it bubbles to the harness CRITICAL handler.

## Deliverables

In `modules/rtl_test/setup.py`:

- `DiscoverConfigFileMod` — walks up the dir tree from CWD for a filename (config:
  `filename:str`, `max_levels:int = 8`); stops at git root or filesystem root; emits the
  resolved `Path`. Zero input ports; runs once via `unit`.
  **Failure handling**: post-loop check — if walked to the root without finding the file,
  call `log.critical(f"{filename} not found walking up from CWD")` (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:35`). `PermissionError` from directory listing
  propagates uncaught (becomes harness CRITICAL via the bubbling-SystemExit catch). See
  [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:16-36` — `_discover_root_cfg`.

**Manifest** — this module opens the `rtl_test/setup.py` block in `modules/config.yaml`
(later appended to by `04b`–`04i`, `05a`–`05f`, `10b`):

```yaml
- file: rtl_test/setup.py
  plugins:
  - { name: discover-config-file, class_name: DiscoverConfigFileMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `tmp_path` nested dirs + `monkeypatch.chdir`
to control CWD; `Config(filename="root_config.yaml", max_levels=…)`; `logging_handler` for
the `log.critical` paths.

- CWD already holds `root_config.yaml` → emits `("default", cwd / "root_config.yaml")` on the
  first iteration (boundary: depth 0).
- File sits `N` levels up with no `.git` between (e.g. `tmp_path/a/b` is CWD, file in
  `tmp_path`) → walk ascends and emits `("default", tmp_path / "root_config.yaml")`.
- A `.git` dir sits between CWD and the file → walk stops at the git boundary, file never
  reached → not-found `log.critical` → `pytest.raises(SystemExit)` (`logging_handler`).
- File absent within the depth limit (`max_levels=2`, file 3 levels up) → loop exhausts →
  not-found `log.critical` → `pytest.raises(SystemExit)` (boundary: `max_levels` exhausted).
- A directory in the walk raises `PermissionError` on `.is_file()` (monkeypatch
  `Path.is_file`) → propagates uncaught → `pytest.raises(PermissionError)`.

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: resolves a fixture `root_config.yaml` from a nested CWD
  and emits its `Path`, stopping at the `max_levels` depth limit (contributes to the
  setup-only end-to-end graph — see [04 index](04-setup-modules.md#acceptance-criteria)).
- Failure idiom exercised: no `root_config.yaml` within `max_levels` → `log.critical`
  (harness exit 1); a `PermissionError` while listing a directory bubbles to the harness
  CRITICAL handler.
- The `modules/config.yaml` manifest entry `{ name: discover-config-file, class_name: DiscoverConfigFileMod }`
  validates and the harness resolves `discover-config-file` → `DiscoverConfigFileMod`.

## Constraints

- `unit` contract, zero-input — runs exactly once.
- Walk at most `max_levels` (default `8`); stop climbing at a git root (`.git` present) or the
  filesystem root (`d == d.parent`).
- Not-found (loop exhausted / boundary reached) → `log.critical` (harness exit 1) — this is a
  setup-domain config error, never a port-routed result. A `PermissionError` while listing a
  directory propagates uncaught (becomes harness CRITICAL via the bubbling-`SystemExit` catch).
- Emit on the string-literal `default` port; stay graph-agnostic.

## Notes

`DiscoverConfigFileMod` is reusable for the harness's own config discovery — see
[07 implementation note](../07-ambiguities-and-assumptions.md).
