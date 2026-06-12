# Spec 01a: Builder schema (`RtlBuilderConfig`)

**Depends on:** none. Can run in parallel with spec 01.
**References:** [01-shared-schema](01-shared-schema.md) (umbrella), [07 settled 1](../07-ambiguities-and-assumptions.md), TODO #9 (resolution).
**Source:** `rtl_buddy/src/rtl_buddy/config/rtl.py:8-126` (`process_opts` + `RtlBuilderConfigOpts` + `RtlBuilderConfig`).

## Before you start

These are `@serde`-decorated dataclasses that the harness never loads directly — a faithful port
of rtl_buddy's config types, so the authoritative reference is the rtl_buddy `config/*.py` source
this spec cites (anchored to `v1.4.0`, commit `a69d962`). The in-repo `@serde` idiom — nested
types and `field(rename=...)` for verbatim YAML field names — is shown by the config-bearing
example in `docs/modules/implementation.md`; [`02 — payload conventions`](../02-payload-conventions.md)
holds the canonical type and `is_pass()` table the port must match. All four schema specs (`01`,
`01a`, `01b`, `01c`) build into the shared `modules/rtl_buddy/schema/` package — coordinate the
module layout with the others.

## Goal

Reimplement `RtlBuilderConfig` and `RtlBuilderConfigOpts` natively so the downstream
consumers (`resolve-builder`, `filter-reglvl`, `build-compile-cmd`, `resolve-seed`,
`build-sim-cmd`) can use the schema by field and method without opening `rtl_buddy`.
Preserves the YAML field-name surface so existing `root_config.yaml` files load
drop-in (see [07 settled 1](../07-ambiguities-and-assumptions.md)).

## Deliverables

A single file, `modules/rtl_buddy/schema/builder.py`, exporting `RtlBuilderConfig`,
`RtlBuilderConfigOpts`, and the `process_opts` helper.

### `process_opts` deserialiser

```python
process_opts = lambda opts: re.sub(r'\s+', ' ', opts).split(' ')
```

Collapses any whitespace run to a single space, then splits on space. A YAML value of
`"-Wall   -Wextra\n  -Werror"` becomes `["-Wall", "-Wextra", "-Werror"]`. Used as the
`deserializer=` for both `compile_time` and `run_time` fields of
`RtlBuilderConfigOpts`. A YAML `None` (i.e. the field is omitted) bypasses the
deserialiser and remains `None`.

Source: `rtl_buddy/src/rtl_buddy/config/rtl.py:8`.

### `RtlBuilderConfigOpts`

Per-mode CLI option lists for one builder. Lives inside `RtlBuilderConfig.opts`, keyed
by mode name (e.g. `"debug"`, `"release"`, `"reg"`).

| field          | type               | YAML rename    | default            | notes                                                       |
|----------------|--------------------|----------------|--------------------|-------------------------------------------------------------|
| `compile_time` | `list[str] \| None`| `compile-time` | required           | Deserialised via `process_opts`. `None` if YAML omits the key. |
| `run_time`     | `list[str] \| None`| `run-time`     | required           | Same deserialiser; same `None` behaviour.                   |

Source: `rtl_buddy/src/rtl_buddy/config/rtl.py:10-20`.

### `RtlBuilderConfig`

One entry per element in `root_config.yaml`'s top-level `cfg-rtl-builder` list. Carries
the executable name, the simv name, the per-mode option lists, and the default seed
plumbing.

| field             | type                              | YAML rename             | default  | notes                                                                                                                                                                |
|-------------------|-----------------------------------|-------------------------|----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name`            | `str`                             | (none)                  | required | Unique builder identifier (e.g. `verilator`, `vcs`). Used by `PlatformConfig.initialise` keyed lookup and by `filter-reglvl` → `TestConfig.get_reglvl(builder_name)`. |
| `exe`             | `str`                             | `builder`               | required | Compiler executable basename. `os.path.basename(exe).startswith("verilator")` switches downstream simv resolution (see Verilator quirk below).                       |
| `simv`            | `str`                             | `builder-simv`          | required | Simulator executable on disk for non-verilator builders.                                                                                                             |
| `sim_rand_seed`   | `int`                             | `sim-rand-seed`         | required | Default seed used by `SeedMode.DEFAULT` (`resolve-seed`).                                                                                                            |
| `sim_rand_prefix` | `str`                             | `sim-rand-seed-prefix`  | required | Simulator-specific CLI fragment prepended to the seed value (e.g. `"+ntb_random_seed="`).                                                                            |
| `opts`            | `dict[str, RtlBuilderConfigOpts]` | `builder-opts`          | required | Per-mode option lists. Indexed by `builder_mode` (the CLI flag).                                                                                                     |

Methods:

| signature                                                       | returns                                                                                                              | log idiom                                                                                                                                                  |
|-----------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `get_name() -> str`                                             | `self.name`                                                                                                          | none                                                                                                                                                       |
| `get_exe() -> str`                                              | `self.exe`                                                                                                           | none                                                                                                                                                       |
| `get_simv() -> str`                                             | `self.simv` (callers handle the verilator override themselves — see below)                                           | none                                                                                                                                                       |
| `get_seed() -> int`                                             | `self.sim_rand_seed`                                                                                                 | none                                                                                                                                                       |
| `get_modes() -> list[str]`                                      | `list(self.opts.keys())`                                                                                             | none                                                                                                                                                       |
| `get_compile_time_opts(mode: str) -> list[str]`                 | a **fresh copy** of `self.opts[mode].compile_time`                                                                   | `log.critical` if `mode not in self.opts` or `self.opts[mode].compile_time is None`; immediate `SystemExit(1)` per [05](../05-branching-and-results.md#log-idioms-per-failure-site). |
| `get_run_time_opts(mode: str, seed: int \| None = None) -> list[str]` | a **fresh copy** of `self.opts[mode].run_time`, with `self.sim_rand_prefix + str(seed)` appended if `seed is not None` | same `log.critical` conditions as `get_compile_time_opts`.                                                                                                  |

Both `get_*_opts` methods return *fresh* lists (rtl_buddy uses `list(...)` at
`rtl.py:102,120`). Mutating the return value must not corrupt the underlying config;
preserve this in the reimplementation.

Source: `rtl_buddy/src/rtl_buddy/config/rtl.py:22-126`.

### Verilator quirk (caller-side convention)

`builder_cfg.get_simv()` always returns the configured value. Verilator builds use a
different convention: the simulator binary sits at `<build_dir>/simv` (where
`build_dir = f"obj_dir_{test_tag}"`), not at `builder_cfg.simv`. Callers
(`build-compile-cmd`, `build-sim-cmd`) MUST switch on:

```python
if os.path.basename(builder_cfg.get_exe()).startswith("verilator"):
    simv_path = f"{build_dir}/simv"
else:
    simv_path = builder_cfg.get_simv()
```

Mirrors `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:73-80`. The detection is on `exe`,
not on `name`, so a builder configured as `name: my-verilator-wrapper, builder:
verilator-bin` is still detected. Keep the switch in callers (not on the schema) so
the schema stays a pure value object.

## Tests (`modules/tests/test_builder_schema.py`)

- **Round-trip.** Load an unmodified rtl_buddy `root_config.yaml` (e.g. from
  `rtl-buddy-proj-template/design/sandbox`); for each `cfg-rtl-builder` entry, every
  field round-trips equal to the equivalent rtl_buddy `RtlBuilderConfig` constructed
  over the same YAML.
- **`process_opts` happy path.** `"-Wall  -Wextra"` → `["-Wall", "-Wextra"]`;
  `"  -single-flag  "` → `["-single-flag"]`; `"a\n\tb"` → `["a", "b"]`.
- **`process_opts` `None` passthrough.** A YAML omitting `compile-time` leaves
  `RtlBuilderConfigOpts.compile_time is None`; same for `run-time`.
- **`get_compile_time_opts("debug")`** returns the deserialised list for that mode.
- **`get_compile_time_opts("missing-mode")`** calls `log.critical` (assert via
  `caplog` plus the bubbling-`SystemExit` contract).
- **`get_compile_time_opts(mode)` where `compile_time is None`** likewise criticals.
- **`get_run_time_opts("debug", seed=42)`** appends `sim_rand_prefix + "42"` to the
  list.
- **`get_run_time_opts("debug")` with no seed** returns the list unchanged.
- **Result freshness.** Mutating the return of `get_compile_time_opts` /
  `get_run_time_opts` does not mutate the underlying `self.opts[mode]` lists.

## Acceptance criteria

- Tests pass.
- Loading an unmodified rtl_buddy `root_config.yaml` produces `RtlBuilderConfig`
  instances whose `get_*` methods return values equal to those produced by
  `from rtl_buddy.config.rtl import RtlBuilderConfig` over the same file.
- Every downstream consumer spec ([05](05-selection-expansion-modules.md),
  [07](07-compile-cycle-modules.md), [08](08-sim-cycle-modules.md)) references methods
  by name (`builder_cfg.get_exe()`, `builder_cfg.get_seed()`,
  `builder_cfg.get_run_time_opts(mode, seed)`, etc.) without forcing the implementer
  to open `rtl_buddy/src/rtl_buddy/config/rtl.py`.

## Constraints

- Preserve the YAML renames exactly (`builder`, `builder-simv`, `sim-rand-seed`,
  `sim-rand-seed-prefix`, `builder-opts`, `compile-time`, `run-time`). Do **not** Pythonify
  them — they are the public surface for drop-in `root_config.yaml` loading.
- `get_compile_time_opts(mode)` / `get_run_time_opts(mode, seed)` must `log.critical`
  (immediate `SystemExit(1)`) when `mode not in self.opts` or the mode's list is `None` — not
  a port-routed result (this is system-wide misconfiguration). See
  [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
- Both `get_*_opts` must return a **fresh** `list(...)` copy — mutating the return must not
  corrupt the underlying `self.opts[mode]` lists.
- `get_run_time_opts` appends `sim_rand_prefix + str(seed)` **only when `seed is not None`**,
  and only once — callers must **not** add the seed again.
- Keep the verilator simv switch in **callers** (on `os.path.basename(get_exe())`), never on
  the schema or on `name` — the schema stays a pure value object.

## Notes

YAML `field(rename=...)` targets are the **public surface** for downstream rtl_buddy
users — do **not** Pythonify them. Preserve hyphens and casing exactly as listed.

`get_modes()` in rtl_buddy returns `self.opts.keys()` (a `dict_keys` view typed as
`list[str]`). The reimplementation should return a true `list[str]` so the signature
is honest; no consumer iterates while mutating, so the change is safe.
