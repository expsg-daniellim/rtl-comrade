# Spec 04a: discover-config-file (`DiscoverConfigFileMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index: [idx-04 — Setup modules](../idx-04-setup.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module **creates** `modules/rtl_buddy/setup.py` — it is the first spec to write the file, so establish the shared imports and module-level helpers here. The file then receives further additions from the rest of the setup chain (`04b`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Implement the run-once tree-walk that locates a named config file by walking up from CWD — the entry point of the setup chain.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
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
        try:
            for _ in range(self.max_levels):
                if (d / self.filename).is_file():
                    return ("default", d / self.filename)
                if d == d.parent:                  # filesystem root
                    break
                d = d.parent
        except PermissionError as e:
            log.fatal("config_discovery_denied", filename=self.filename, dir=str(d), exc_info=e)
        log.fatal("config_not_found", filename=self.filename)
```

## Algorithm

1. Seed the walk at the current directory: `d = Path.cwd()`.
2. Loop at most `self.max_levels` times. If `(d / self.filename).is_file()`, the file is found — emit `("default", d / self.filename)` and return.
3. Stop climbing at the filesystem root: if `d == d.parent`, break. Otherwise ascend (`d = d.parent`) and repeat step 2.
4. **Failure — not found.** Falling out of the loop (depth limit hit, or a boundary reached with no match) is the not-found case: `log.fatal(f"{self.filename} not found walking up from CWD")` (harness exits 1). A `PermissionError` raised while walking (an unreadable directory) is **caught** and converted to its own `log.fatal("config_discovery_denied", …)` — the module handles its own errors rather than relying on the harness backstop.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `DiscoverConfigFileMod` — walks up the dir tree from CWD for a filename (config: `filename:str`, `max_levels:int = 8`); stops at the filesystem root; emits the resolved `Path`. Zero input ports — that is what bounds it to one invocation, so it uses the `default` contract (`unit` would be identical here and assert a guarantee it does not provide).
  **Failure handling**: post-loop check — if walked to the root without finding the file, call `log.fatal(f"{filename} not found walking up from CWD")` (mirrors `rtl_buddy/src/rtl_buddy/config/root.py:35`). A `PermissionError` from an unreadable directory in the walk is **caught** and converted to `log.fatal("config_discovery_denied", …)` — the module catches its own errors; the harness backstop is a fallback, not relied on. See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:16-36` — `_discover_root_cfg`.

**Manifest** — this module opens the `rtl_buddy/setup.py` block in `modules/config.yaml` (later appended to by `04b`–`04i`, `05a`–`05f`, `10b`):

```yaml
- file: rtl_buddy/setup.py
  plugins:
  - { name: discover-config-file, class_name: DiscoverConfigFileMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `tmp_path` nested dirs + `monkeypatch.chdir` to control CWD; `Config(filename="root_config.yaml", max_levels=…)`; `logging_handler` for the `log.fatal` paths.

- CWD already holds `root_config.yaml` → emits `("default", cwd / "root_config.yaml")` on the first iteration (boundary: depth 0).
- File sits `N` levels up (e.g. `tmp_path/a/b` is CWD, file in `tmp_path`) → walk ascends and emits `("default", tmp_path / "root_config.yaml")`.
- File absent within the depth limit (`max_levels=2`, file 3 levels up) → loop exhausts → not-found `log.fatal` → `pytest.raises(typer.Exit)` (boundary: `max_levels` exhausted).
- A directory in the walk raises `PermissionError` on `.is_file()` (monkeypatch `Path.is_file`) → caught → `log.fatal("config_discovery_denied", …)` → `pytest.raises(typer.Exit)` (assert via `caplog`).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: resolves a fixture `root_config.yaml` from a nested CWD and emits its `Path`, stopping at the `max_levels` depth limit.
- Failure idiom exercised: no `root_config.yaml` within `max_levels` → `log.fatal` (harness exit 1); a `PermissionError` while walking is caught → `log.fatal("config_discovery_denied", …)` (harness exit 1).
- The `modules/config.yaml` manifest entry `{ name: discover-config-file, class_name: DiscoverConfigFileMod }` validates and the harness resolves `discover-config-file` → `DiscoverConfigFileMod`.

## Constraints

- `default` contract, zero-input — runs exactly once (zero input ports bound the invocation, not the contract).
- Walk at most `max_levels` (default `8`); stop climbing only at the filesystem root (`d == d.parent`).
- Not-found (loop exhausted / boundary reached) → `log.fatal` (harness exit 1) — this is a setup-domain config error, never a port-routed result. A `PermissionError` while walking is caught and converted to `log.fatal` — the module catches its own errors rather than relying on the harness backstop.
- Emit on the string-literal `default` port; stay graph-agnostic.
