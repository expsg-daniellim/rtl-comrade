# Spec 01: resolve-reg-config-path (`ResolveRegConfigPathMod`)

**Depends on:** nothing — the module is self-contained.
**References:** [00-overview](00-overview.md); `rtl_buddy/src/rtl_buddy/rtl_buddy.py:372-393` — `do_rtl_regression` `reg_config` default logic; `rtl_buddy/src/rtl_buddy/config/root.py:101-104` — the root-config fallback, joined onto the directory containing `root_config.yaml`.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms).

## Goal

Bridge the CLI default to rtl_buddy's behaviour: if `reg_config` is empty, pull the path from `root_cfg.cfg_rtl_reg.path` and resolve it relative to the directory containing `root_config.yaml` (`root_cfg_path.parent`); else resolve the CLI value against the current working directory. Atomic so the default-resolution lives in one place.

## Surface

```
contract:          unit
inputs:            root_cfg:RootConfig, root_cfg_path:Path, reg_config:str = ""
outputs:           default → Path
```

```python
class ResolveRegConfigPathMod:
    def run(self, root_cfg:RootConfig, root_cfg_path:Path, reg_config:str = ""):
        try:
            if reg_config:
                path = Path(reg_config).resolve()
            else:
                path = (root_cfg_path.parent / root_cfg.cfg_rtl_reg.path).resolve()
        except ValueError as e:
            log.fatal("reg_config_path_invalid", reg_config=reg_config, message=str(e), exc_info=e)
        except RuntimeError as e:
            log.fatal("reg_config_path_symlink_loop", reg_config=reg_config, message=str(e), exc_info=e)
        except OSError as e:
            log.fatal("reg_config_path_os_error", reg_config=reg_config, err=e.strerror, errno=e.errno, exc_info=e)
        return ("default", path)
```

## Algorithm

1. If `reg_config` is non-empty, resolve it as a `Path`.
2. Otherwise, join `root_cfg.cfg_rtl_reg.path` onto `root_cfg_path.parent` and resolve that.
3. Catch `resolve()` failures in either branch per the code sample: `ValueError` (e.g. an embedded null character), `RuntimeError` (symlink loop on Python ≤ 3.12) and `OSError` (symlink loop on Python ≥ 3.13, or a deleted working directory when resolving a relative path).
4. Return the resolved `Path` on `default`.

## Deliverables

- `ResolveRegConfigPathMod` in `modules/rtl_buddy/setup.py`.
- **Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`:
  ```yaml
    - { name: resolve-reg-config-path, class_name: ResolveRegConfigPathMod }
  ```

## Tests

In `modules/tests/test_setup.py`. No fixtures beyond a stub `RootConfig` and a `root_cfg_path` (e.g. under `tmp_path`); the fallback case must use a `root_cfg_path` outside the current working directory so a CWD-relative resolution fails it.

- `(reg_config="path/to/reg.yaml", root_cfg=..., root_cfg_path=...)` → returns `("default", Path("path/to/reg.yaml").resolve())` — `root_cfg_path` is ignored.
- `(reg_config="", root_cfg=<root with cfg_rtl_reg.path="design/regression.yaml">, root_cfg_path=tmp_path / "root_config.yaml")` → returns `("default", (tmp_path / "design/regression.yaml").resolve())`.
- `reg_config` containing an embedded null character → `log.fatal("reg_config_path_invalid")`.
- `Path.resolve` raising `RuntimeError` (patched) → `log.fatal("reg_config_path_symlink_loop")`.
- `Path.resolve` raising `OSError` (patched) → `log.fatal("reg_config_path_os_error")`.

Each error test asserts the event name passed to `log.fatal` (e.g. by wrapping it with `unittest.mock.patch(..., wraps=...)`), not only that `typer.Exit` is raised.

## Acceptance criteria

- All five test cases pass.
- `resolve-reg-config-path` → `ResolveRegConfigPathMod` resolves in the manifest.
- An explicit `reg_config` string is used as-is (resolved to absolute).
- An empty `reg_config` falls back to `root_cfg.cfg_rtl_reg.path`, resolved relative to the directory containing `root_config.yaml`, not the current working directory.
- A path that fails to resolve aborts via `log.fatal` with a distinct event name.

## Docs

Add a `docs/modules/resolve-reg-config-path.md` page (with a Failure routing section listing the three events) and update `docs/modules/index.md` to include it. Follow `docs/creating-documentation.md` and `docs/modules/doc-structure.md`.

## Constraints

- **No graph knowledge.** The module does not know about `parse-reg-config` or the graph; it resolves one path.
- **Contract: `unit`.** All inputs arrive once — `reg_config` from a CLI edge, `root_cfg` from `parse-root`, `root_cfg_path` from `discover-root`.
