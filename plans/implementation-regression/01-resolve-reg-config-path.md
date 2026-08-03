# Spec 01: resolve-reg-config-path (`ResolveRegConfigPathMod`)

**Depends on:** nothing — the module is self-contained.
**References:** [00-overview](00-overview.md); `rtl_buddy/src/rtl_buddy/rtl_buddy.py:372-393` — `do_rtl_regression` `reg_config` default logic.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms).

## Goal

Bridge the CLI default to rtl_buddy's behaviour: if `reg_config` is empty, pull the path from `root_cfg.cfg_rtl_reg.path`; else use the CLI value as-is. Atomic so the default-resolution lives in one place.

## Surface

```
contract:          unit
inputs:            reg_config:str = "", root_cfg:RootConfig
outputs:           default → Path
```

```python
class ResolveRegConfigPathMod:
    def run(self, reg_config:str, root_cfg:RootConfig):
        if reg_config:
            path = Path(reg_config).resolve()
        else:
            path = Path(root_cfg.cfg_rtl_reg.path).resolve()
        return ("default", path)
```

## Algorithm

1. If `reg_config` is non-empty, resolve it as a `Path`.
2. Otherwise, read `root_cfg.cfg_rtl_reg.path` and resolve that.
3. Return the resolved `Path` on `default`.

## Deliverables

- `ResolveRegConfigPathMod` in `modules/rtl_buddy/setup.py`.
- **Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`:
  ```yaml
    - { name: resolve-reg-config-path, class_name: ResolveRegConfigPathMod }
  ```

## Tests

In `modules/tests/test_setup.py`. Pure function — no fixtures beyond a stub `RootConfig`.

- `(reg_config="path/to/reg.yaml", root_cfg=...)` → returns `("default", Path("path/to/reg.yaml").resolve())`.
- `(reg_config="", root_cfg=<root with cfg_rtl_reg.path="design/regression.yaml">)` → returns `("default", Path("design/regression.yaml").resolve())`.

## Acceptance criteria

- Both test cases pass.
- `resolve-reg-config-path` → `ResolveRegConfigPathMod` resolves in the manifest.
- An explicit `reg_config` string is used as-is (resolved to absolute).
- An empty `reg_config` falls back to `root_cfg.cfg_rtl_reg.path`.

## Docs

Add a `docs/modules/resolve-reg-config-path.md` page and update `docs/modules/index.md` to include it. Follow `docs/creating-documentation.md` and `docs/modules/doc-structure.md`.

## Constraints

- **No graph knowledge.** The module does not know about `parse-reg-config` or the graph; it resolves one path.
- **Contract: `unit`.** Both inputs arrive once — `reg_config` from a CLI edge, `root_cfg` from `parse-root`.
