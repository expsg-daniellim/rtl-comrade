# Spec 04g: ensure-logs-dir (`EnsureLogsDirMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md),
[07 settled 25 / 26](../07-ambiguities-and-assumptions.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

## Goal

Bootstrap the artefact directory (`<work_dir>/logs` by default) once at startup, ahead of any
subprocess, so no downstream writer needs its own `mkdir`, and **emit the resolved directory as
data** so the path composers root onto a provided directory instead of the ambient CWD.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.
`work_dir` is a **load-bearing** input (the validated base directory from `check-suite-cwd`) —
it is read to root the logs directory, so it is a required (non-defaulted) port the harness
edge-validates. This node takes **no** `env_ready` input and emits **no** `env_ready` token: the
`logs/` `mkdir` it performs is ordered ahead of every subprocess by the `logs_dir` **data** edge
(the composers block on `logs_dir` before building a command, and the directory is created before
that value is emitted), while the PATH prepend is sequenced separately by `prepend-cwd-path →
run-process.env_ready` (`required: true`). See [07 settled 25/26](../07-ambiguities-and-assumptions.md).

```
contract: unit
inputs:   work_dir:Path, logs_dir:str = "logs"
outputs:  logs_dir → Path   (resolved artefact dir → cc-build / sim-build / resolve-seed)
```

```python
class EnsureLogsDirMod:
    def run(self, work_dir:Path, logs_dir:str = "logs"):
        path = Path(work_dir) / logs_dir          # rooted on the validated base dir, not ambient CWD
        path.mkdir(parents=True, exist_ok=True)    # OSError/PermissionError → harness CRITICAL
        log.info("logs_dir_ready", path=str(path.resolve()))
        return ("logs_dir", path)                  # resolved dir → path composers (first-run-required input)
```

## Algorithm

1. Resolve the artefact directory against the provided base: `path = Path(work_dir) / logs_dir`.
   `work_dir` is the validated base directory emitted by `check-suite-cwd` (its sole artefact-
   location source); `logs_dir` is the **subdirectory name** (CLI `--logs-dir`, default
   `"logs"`). The location no longer depends on the ambient process CWD.
2. Create it idempotently: `path.mkdir(parents=True, exist_ok=True)` — `exist_ok=True` makes
   re-runs a no-op; `parents=True` accepts nested names like `build/logs`.
3. Record it for auditability: `log.info("logs_dir_ready", path=str(path.resolve()))`.
4. Emit one port: `("logs_dir", path)` — the **resolved directory**, consumed as a
   first-run-required persistent input by `build-compile-cmd` / `build-sim-cmd` / `resolve-seed`
   so they join filenames onto a ready-made path. Because the `mkdir` runs *before* this value is
   emitted and those consumers block on it before composing a command, the directory provably
   exists before any subprocess redirects into it — no `env_ready` token is needed for the `mkdir`
   ordering. The composers no longer re-derive the directory from a bare `logs_dir` name, so the
   CWD-relative assumption lives nowhere but the `check-suite-cwd` → `ensure-logs-dir` provider pair.
5. **Failure — unwritable parent.** A `PermissionError`/`OSError` from `mkdir` is a
   setup-domain config error, left to propagate uncaught (harness CRITICAL via the
   bubbling-SystemExit catch, same idiom as `DiscoverConfigFileMod`) — no port-routed fail.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `EnsureLogsDirMod` — bootstraps the artefact directory and **emits its resolved path** for
  `cc-build`, `sim-build`, and `resolve-seed` (REPLAY) to compose log/randseed paths onto. Mirrors
  `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` (`output_dir = "logs"; if not
  os.path.exists(...): os.makedirs(...)`), but lifted out of `VlogSim.__init__`'s
  per-test lazy mkdir into a single explicit setup node so:
  (i) no downstream writer needs its own `mkdir`,
  (ii) the directory is created exactly once per invocation, ahead of any subprocess, and
  (iii) artefact location is decided **once** (by `check-suite-cwd`'s `work_dir`) and flows as
  data, instead of every writer re-deriving it from the ambient CWD.
  Takes `work_dir:Path` from `check-suite-cwd` (the validated base directory — **load-bearing**,
  read to root the logs dir, so a missing edge fails edge-validation rather than silently
  mistargeting) and the CLI `logs_dir:str` subdirectory name (default `"logs"`; `rtl_buddy` has no
  override, this is a small Notable divergence — see [07](../07-ambiguities-and-assumptions.md)).
  Takes **no** `env_ready` and emits **no** `env_ready`: the PATH prepend is sequenced directly by
  `prepend-cwd-path → run-process.env_ready` (`required: true`), and this node's `mkdir` is ordered
  by the `logs_dir` **data** edge (it `mkdir`s *before* emitting `logs_dir`, and the composers
  block on that value before building a command, so the directory exists before any redirect).
  Runs once via `unit`. See [Algorithm](#algorithm) for the numbered steps.
  Emits `("logs_dir", path)` — the resolved `Path(work_dir) / logs_dir` — as a **first-run-required
  persistent input** consumed by the path composers. The path is **not** stamped into `ctx`; it is
  the resolved directory the composers join filenames onto. The two legs name files differently:
  - **compile leg** (`build-compile-cmd`, spec [07a](07a-build-compile-cmd.md)):
    `logs_dir / f"{test_tag}.compile.log"` and `.compile.err`, where
    `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test_name)` — the **sanitised** build tag
    (rtl_buddy `_get_build_tag`, `tools/vlog_sim.py:61-65`). Example: test `my_test` →
    `<work_dir>/logs/my_test.compile.log`.
  - **sim leg** (`build-sim-cmd` / `resolve-seed`, specs
    [08c](08c-build-sim-cmd.md) / [08b](08b-resolve-seed.md); `write-randseed`
    [08d](08d-write-randseed.md) consumes the pre-composed path from `sim_cmd`):
    `logs_dir / f"{test_name}{run_suffix}.log"`, `.err`, and `.randseed`, off the **raw**
    `test_name`, where `run_suffix` is `""` when `ctx["run_id"] is None` and
    `f"_{run_id:04d}"` (the run-id zero-padded to four digits) otherwise — rtl_buddy
    `_get_log_path` (`tools/vlog_sim.py:82-86`). Examples: a single run of `my_test` →
    `<work_dir>/logs/my_test.log`; run-id 3 → `<work_dir>/logs/my_test_0003.randseed`.
  **Failure handling**: `PermissionError` / `OSError` from `mkdir` propagate uncaught
  (becomes a harness CRITICAL via the bubbling-SystemExit catch, same idiom as
  `DiscoverConfigFileMod`'s `PermissionError`). No port-routed fail — this is a setup-domain
  config error, not per-test.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` — the `output_dir = "logs"` mkdir in `VlogSim.__init__` (lifted to a setup node; rooting on `work_dir` and emitting the resolved path are divergences in this plan — see [07 settled 26](../07-ambiguities-and-assumptions.md)).

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: ensure-logs-dir, class_name: EnsureLogsDirMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `tmp_path` as the `work_dir`;
`logging_handler` for the failure path.

- `work_dir=tmp_path`, `logs_dir="logs"`, no pre-existing dir → emits `("logs_dir",
  tmp_path/"logs")`; `tmp_path/"logs"` now exists.
- `work_dir=tmp_path`, `logs_dir="logs"` with the dir pre-existing → same emissions, no
  exception (idempotent via `exist_ok=True`).
- `work_dir=tmp_path`, `logs_dir="build/logs"`, no pre-existing `build/` → emits the resolved
  `tmp_path/"build/logs"` and both `build/` and `build/logs/` now exist (boundary: nested,
  verifies `parents=True`).
- Resolved path roots on `work_dir`, **not** the process CWD: with the process CWD set
  elsewhere (`monkeypatch.chdir(other)`), `work_dir=tmp_path`, `logs_dir="logs"` still creates
  `tmp_path/"logs"` (boundary: location follows the provided base dir).
- `work_dir` pointing into a read-only parent → `mkdir` raises `PermissionError`, propagates
  uncaught → `pytest.raises(PermissionError)` (mirrors `DiscoverConfigFileMod`).

## Acceptance criteria

- Tests pass.
- Output port exercised: `logs_dir` emits the resolved `Path(work_dir) / logs_dir` (default
  `<work_dir>/logs`), leaving the directory present on disk before any later main-line node fires
  (contributes to the setup-only end-to-end graph — see
  [04 index](04-setup-modules.md#acceptance-criteria)).
- Location follows `work_dir`, not the ambient CWD — the path composers receive the resolved
  directory and never re-derive it.
- Failure idiom exercised: an `OSError`/`PermissionError` creating the directory bubbles to the
  harness CRITICAL handler (exit 1).
- The `modules/config.yaml` manifest entry `{ name: ensure-logs-dir, class_name: EnsureLogsDirMod }`
  validates and the harness resolves `ensure-logs-dir` → `EnsureLogsDirMod`.

## Constraints

- `unit` contract, runs once — create the directory with `(Path(work_dir) /
  logs_dir).mkdir(parents=True, exist_ok=True)` (idempotent; nested names allowed).
- `work_dir` is **load-bearing** — it is read to root the logs directory (so it is a required,
  non-defaulted port the harness edge-validates). The node takes **no** `env_ready` input.
- Do **not** root the directory on the ambient process CWD (`Path(logs_dir).mkdir()` is wrong) —
  always join `logs_dir` onto the provided `work_dir`.
- Emit the resolved `Path` on the `logs_dir` port (consumed as a persistent input by
  `build-compile-cmd`/`build-sim-cmd`/`resolve-seed`); do **not** stamp it into `ctx`. Those
  composers join filenames onto it — they must not re-derive the directory from a bare name. The
  `mkdir` must run **before** the emit, so the value's arrival attests the directory exists.
- `PermissionError`/`OSError` from `mkdir` propagate uncaught (harness CRITICAL) — no
  port-routed fail; this is a setup-domain error, not per-test.
- Do **not** add an `env_ready` input or output — the `mkdir` ordering is carried by the `logs_dir`
  data edge, and the PATH prepend by `prepend-cwd-path → run-process.env_ready` (`required: true`).

## Notes

`EnsureLogsDirMod` is wired in `test`/`randtest` only: regression's per-suite `chdir`
means a once-at-startup bootstrap targets the wrong place; the regression
equivalent runs **per chdir'd suite** and is owned by [08](../08-sibling-graphs.md).
Because the directory is now rooted on the `work_dir` *input* rather than the ambient CWD, the
regression equivalent differs only in **which `work_dir` it is fed** (the per-suite base),
not in any path logic here — the centralisation makes that sibling cheaper, not harder.

This node carries **no ordering token at all** — both `work_dir` (in) and `logs_dir` (out) are
real data the consumers read, so their edges are required and validated, and the `mkdir`-before-
subprocess ordering falls out of the `logs_dir` data dependency for free. Earlier drafts threaded
an `env_ready` token through this node (`prepend-path → ensure-logs → cc-run/sim-run`) to fold the
PATH prepend and the `mkdir` into one sequencing surface; that relay was removed once the
`required: true` edge marking (see [07 settled 25](../07-ambiguities-and-assumptions.md)) let
`prepend-cwd-path` sequence the PATH prepend directly onto each `run-process`, and once it was
clear the `mkdir` was already ordered by the `logs_dir` data edge. Removing it restores this
node's atomicity (it now depends only on what it reads). The earlier `_cwd` ordering-only token —
whose defaulted-port exemption (Settled item 21) meant a forgotten edge silently skipped the
guard — is likewise gone; `work_dir` is the load-bearing, validated replacement.
