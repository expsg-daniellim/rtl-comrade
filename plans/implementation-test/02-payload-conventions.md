# Payload conventions

Modules receive raw values (the harness unwraps `Payload` before calling `run`). There is
**no single payload type** threaded through the graph. Instead there are three small,
purpose-specific payload shapes, plus one correlation key. The shapes are dataclasses in
`modules/rtl_buddy/schema/payloads.py` (spec [01](specs/01-shared-schema.md)). Two properties
are decided **per type, not blanket**:

- **the correlation key** is the field `keyed_join` matches on, named by the contract's
  `keyed_field` (default `"key"`; `contracts/keyed_join.py::_key_of` reads it attribute-first,
  falling back to a dict entry). A payload carries its **own** `key` field exactly when the key
  *is its own identity*; otherwise the key rides the `KeyedValue` envelope. Three cases:
  - **`TestConfig` self-keys.** The `test` edge carries one scheduled-test instance, and `key`
    (`name#sweep#run`) *is* that instance's identity — so it lives on the object, which rides
    the `test` edge **bare** (no envelope). `key` is a runtime-only field on `TestConfig`
    ([01b](specs/01b-suite-schema.md)), set to `name` at construction and refined at the fan-outs,
    read by `keyed_join` attribute-first. Distinct from `name`, which collides across sweep
    variants and run-ids.
  - **Multi-field messages self-key** (`Command`/`Proc`/`RandSeed`/`RandSeedDone`) —
    cohesive purpose-built messages, so the key is naturally one of their fields, no envelope.
    **`TestResult`** likewise self-keys: its `key` is the producing test invocation's id, so
    result ports emit the `TestResult` directly — there is no `Result(key, result)` wrapper.
  - **Everything else rides `KeyedValue`** because the key is *not the value's own identity*: a
    primitive (`int`/`Path`/`str`) has no identity at all, and **`model`** is the `ModelConfig`
    resolved *for a test* — keyed by the **test's** identity (so `write-filelist` can join it
    back), which is foreign to the model. Stamping the test's key onto the model value object
    would misrepresent a correlation id as the model's own; the envelope keeps it honest.

  The key is *not* universal: non-keyed payloads (broadcast config singletons, pure ordering
  signals below) carry none and are never correlated.
- **`frozen=True`** on the envelope and message payloads (`KeyedValue`, `Command`, `Proc`, …).
  Freezing blocks rebinding a dataclass's own fields (`kv.value = …`), which no node does —
  edges are built once at the fan-outs. It does **not** block mutating the object a field points
  at, so `run-preproc` mutating a wrapped value would still work; but the `test` edge is **not**
  wrapped — `run-preproc` mutates the bare `TestConfig` directly (`set_plusarg`, …), which is
  fine because `TestConfig` is itself unfrozen ([01b](specs/01b-suite-schema.md)). The
  still-enveloped `model` edge is a frozen `KeyedValue` around a frozen `ModelConfig`.

## The correlation key

A stable string identifying one test invocation. Its **base value is the test's name**, defaulted
by `TestConfig.__post_init__` ([spec 01b](specs/01b-suite-schema.md)) — so every `TestConfig` is
born self-keyed regardless of construction site, and `select` forwards it unchanged. It is then
suffixed at each fan-out **that actually produces variants**:

- *construction* → `key = "<test_name>"` (the base; `select`/`filter` carry it through untouched)
- `sweep`  → `key = "<test_name>#<sweep_idx>"` **per produced variant**; a test with no sweep
  script passes through with its key **unchanged** (see [spec 05f](specs/05f-expand-sweep.md))
- `runs`   → `key = "<test_name>[#<sweep_idx>]#<run_id>"` when `run_id is not None`; for the
  plain `test` command `run_ids = [None]`, so the key is **unchanged** (see
  [spec 08a](specs/08a-expand-runs.md))

The suffix is only added when the fan-out emits more than the single passthrough item; the
invariant the joins rely on is uniqueness, not a fixed `#i#run` shape.

The key exists so the `keyed_join` nodes can correlate a node's inputs back to the test
they came from. Under the split it appears on **every keyed main-line edge** — on the
`TestConfig` itself for the `test` edge, on the `KeyedValue` wrapper for the rest — and each
`keyed_join` reads `payload.key` (attribute-first) to match its ports, indifferent to whether
that's a field on the object or on the envelope. (Config singletons reach those same nodes as
non-keyed `persistent_inputs`; they carry no key and are broadcast to all keys rather than
correlated.) Modules copy the key forward; they never parse or branch on it.

## Shape 1 — the split per-test/per-run edges

Per-test data rides the main line as **separate keyed edges**. The `test` edge carries a **bare, self-keyed `TestConfig`** (the key is its own identity); every other single-value edge rides the generic frozen `KeyedValue[T]` envelope (`key: str`, `value: T`) because its key is *not* its own identity. The edge name says what rides it:

```python
test     = <TestConfig key="alu_smoke#0#0">            # bare TestConfig (self-keyed)   select → … → post-sim (long-lived); mutated in place by run-preproc, re-keyed via replace at expand-runs
model    = KeyedValue(k, <ModelConfig>)                # KeyedValue[ModelConfig]  load-model → write-filelist (k = the test's key — foreign to the model)
simv     = KeyedValue(k, <str>)                        # KeyedValue[str]          build-compile-cmd → … → build-sim-cmd, then dies
run_id   = KeyedValue(k, int | None)                   # KeyedValue[int|None]     expand-runs → … → build-sim-cmd, then dies
seed     = KeyedValue(k, int)                          # KeyedValue[int]          resolve-seed → build-sim-cmd, then dies
timeout  = KeyedValue(k, float | None)                 # KeyedValue[float|None]   build-sim-cmd → sim-run
filelist = KeyedValue(k, <Path>)                       # KeyedValue[Path]         write-filelist → build-compile-cmd
```

The envelope wraps every Shape-1 edge **except `test`**, because the key on those edges is not the value's own identity: a primitive has no fields *and* no identity, and `model` is keyed by the **test's** identity (so `write-filelist` can join it back), foreign to the `ModelConfig`. `TestConfig` is the one value whose riding key *is* its own — the scheduled-test instance — so it holds `key` directly and rides the `test` edge bare. (Multi-field messages also self-key, Shape 2.)

- **`key` on `TestConfig`** is the synthesized correlation string, a runtime-only field ([01b](specs/01b-suite-schema.md)) set to `name` at construction and re-suffixed at the fan-outs (`sweep`→`name#i`, `expand-runs`→`name#i#run`). `keyed_join` reads it via `keyed_field` (default `"key"`) attribute-first → `test.key`. Nothing *intrinsic* (i.e. `name`) is unique post-fan-out, so the synthesized field is required.
- **`KeyedValue.value`** is the generic single-value slot for the enveloped edges: the edge name conveys the type, so one `KeyedValue[T]` serves `model`/`simv`/`seed`/… rather than a named class per edge (`seed.value` the int, `model.value` the `ModelConfig`, …). *Multi-field* cohesive messages (`proc`, `command`, `randseed`) get their own named dataclasses instead (Shape 2).
- **Edge lifetimes are bounded and visible:** `test` threads the whole pipeline; `model` lives `[load-model, write-filelist]`; `simv` lives `[build-compile-cmd, build-sim-cmd]`; `run_id` `[expand-runs, build-sim-cmd]`; `seed` `[resolve-seed, build-sim-cmd]` — `simv`/`run_id`/`seed` all die at `build-sim-cmd`.
- **`test` is the live `TestConfig`** (not `test.value` — there is no envelope), mutated in-place by `run-preproc` (it is unfrozen, [01b](specs/01b-suite-schema.md)). `expand-runs` re-keys it per run via `dataclasses.replace(test, key=nk)` — a shallow copy that overrides `key` only, sharing `pa`/`pd`/`tb` by reference; safe because `run-preproc` is the sole mutator and runs strictly upstream. The resolved `ModelConfig` is **not** on it — it rides the separate `model` edge (`KeyedValue[ModelConfig]`, produced by `load-model`, `keyed_join`ed at `write-filelist`). These reimplement rtl_buddy `TestConfig` (`config/test.py:43-302`) and `ModelConfig` (`config/model.py:9-51`); renames pinned in specs [01b](specs/01b-suite-schema.md)/[01c](specs/01c-model-schema.md). The `seed_mode` payload is the `SeedMode` enum (`seed_mode.py:4-7`).
- **No `result` field, ever.** Terminal outcomes leave as Shape-3 result edges.
- **Why split, not bagged:** the per-field edges expose true data dependencies (each node's inputs = exactly what it reads) and let `keyed_join` correlate by key rather than relying on lockstep arrival order. Config singletons (`builder_cfg`, `logs_dir`, …) reach the command-builders as `persistent_inputs` on those same `keyed_join` nodes. Full rationale + the node/contract/edge table + edge-wiring list: [`06-graph-yaml.md`](06-graph-yaml.md).

## Shape 2 — multi-field cohesive messages

Payloads produced whole by one node for specific consumers, carrying the key so a `keyed_join` can match. These get **their own named dataclass** (not the generic `KeyedValue[T]` envelope) because each is one cohesive message with several parts produced in one shot:

```python
command       = Command(k, argv=[ ... ],                     # build-*-cmd     → run-process
                        stdout_path=Path, stderr_path=Path)
proc          = Proc(k, rc=int | None,                       # run-process     → interpret-* (rc is None ⟺ timed out;
                     stdout_path=Path, stderr_path=Path)      #                   sim leg → write-randseed gate + link-latest)
randseed      = RandSeed(k, seed=int, randseed_path=Path,    # build-sim-cmd   → write-randseed + link-latest
                        argv=[ ... ])                         #                   (argv: the hier_inst_seed check)
randseed_done = RandSeedDone(k)                              # write-randseed  → link-latest (ordering signal only)
```

`proc` echoes the redirect paths (`stdout_path`/`stderr_path` = the sim log/err), so the post-sim parsers read the log from `proc` (the sim command's parts ride `command` + `randseed`). Single-value edges (`filelist`, `seed`, `timeout`) use the `KeyedValue[T]` envelope (Shape 1). These never accumulate; each is consumed by exactly the next stage(s).

## Shape 3 — result payloads (terminal; fanned into `results-summary`)

The single shape every terminal output port emits, regardless of which stage produced it — the self-keyed `TestResult` directly (no `Result` wrapper). It carries `test_name` (the test's `get_name()`, the summary table's first column):

```python
result = TestResult(key=k, test_name=name, type_=ResultType.…, result="PASS|FAIL|NA|SKIP", desc=…)
```

Emitted on a stage's result port (`skip`, `stop`, `fail`, `timeout`, `result`). Since the
in-graph summary returned (spec [10d](specs/10d-summarise-results.md)) these 13 result ports
are **wired** — each fans into the `results-summary` node via the `any` contract, which renders
the consolidated table from its `finalise()`. The table reads the `TestResult` fields directly, so
`test_name` rides the payload (enrich-over-`key`); there is no `aggregate-results` collector and no
relay — the contract fans straight into the accumulating sink.

A `TestResult`-producing terminal **logs only the errors it encounters** — never a PASS, SKIP, or
early-stop (those outcomes are recorded by the `TestResult` they emit, the summary row). The
**failure** terminals (`interpret-compile`→`compile_failed`, `interpret-sim`→`sim_timeout`,
`load-model`/`expand-sweep`/`run-preproc`/`write-filelist`/`resolve-seed`→ per-exception events
(`model_*`/`sweep_*`/`preproc_*`/`filelist_*`/`replay_seed_*`), and `parse-log`/`parse-uvm-log` on
FAIL/NA → `parse_log_*`/`parse_uvm_*`) `log.error` once under their per-case event name — an exit
driver (`handler.failure`), alongside the consolidated `results-summary.finalise()` FAIL check
(spec [10d](specs/10d-summarise-results.md)). **`early-stop-gate`** is the one NA that drives no
exit: a user-requested stop is not a failure, so it emits no `log.error` and its NA is not a FAIL
row → exit 0 (deliberate divergence from rtl_buddy; see
[07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).

The `<TestResult>` object is the single source for both the table (via `results-summary`) and the
`is_pass()` classification behind the per-case `log.error`. See
[05](05-branching-and-results.md) and [spec 10d](specs/10d-summarise-results.md).

## `TestResult` values used at the result ports

`TestResult` is the single reimplemented value object in `results.py` (spec [01](specs/01-shared-schema.md)) — `key`, `type_: ResultType`, `result`, `desc`, with `is_pass()` true for `PASS`/`SKIP`. `type_` names the originator, `result` the verdict (a faithful port of rtl_buddy's `runner/test_results.py:10-78` *semantics*, not its class hierarchy — the subclasses are collapsed into one dataclass + `@classmethod` constructors). Each terminal builds its value via the matching constructor, passing `test_name` (the test's `get_name()`) as the second positional: `TestResult.compile_fail(key, test_name)`, `TestResult.sim_timeout(key, test_name)`, `TestResult.early_stop(key, test_name, desc)`, `TestResult.skip(key, test_name, desc)`, and `TestResult.parse(key, test_name, result, desc)` for the parse verdicts. The generic per-test FAIL (`load-model`/`expand-sweep`/`run-preproc`/`write-filelist`/`resolve-seed`) uses `TestResult.prep(key, test_name, desc)` (`type_=PREP`, verdict `"FAIL"`), which replaces the old `make_fail_result`.

| result port (node) | factory (`type_`, verdict) | is_pass? | exit contribution |
|---|---|---|---|
| `skip` (`filter`) | `TestResult.skip(key, test_name, desc)` (`SKIP`, SKIP) | yes (SKIP) | none |
| `stop` (`gate-*`) | `TestResult.early_stop(key, test_name, desc)` (`EARLY_STOP`, NA) | no (NA) | **exit 0** (deliberate divergence — see below) |
| `fail` (`interpret-compile`) | `TestResult.compile_fail(key, test_name)` (`COMPILE_FAIL`, FAIL) | no (FAIL) | exit 1 |
| `timeout` (`interpret-sim`) | `TestResult.sim_timeout(key, test_name)` (`SIM_TIMEOUT`, FAIL) | no (FAIL) | exit 1 |
| `fail` (`load-model`/…/`resolve-seed`) | `TestResult.prep(key, test_name, desc)` (`PREP`, FAIL) | no (FAIL) | exit 1 |
| `default` (`parse-log` / `parse-uvm-log`) | `TestResult.parse(key, test_name, result, desc)` (`PARSE`, PASS/FAIL/NA) | PASS→yes | non-pass→exit 1 |

`TestResult.is_pass()` is the single source of truth for the exit code (SKIP counts as
pass; NA/FAIL do not), exactly as in `rtl_buddy` — **except `early-stop`**: the early-stop result
is NA (and `rtl_buddy` exits 1 on `--early-stop`), but this plan treats a user-requested stop as a
non-failure and exits 0. This is the one deliberate exit-code divergence
([07 — Notable divergences](07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).
A genuine NA verdict from `parse-log`/`parse-uvm-log` still drives exit 1.

## Sentinels

`EndSentinel` (handled entirely by contracts) is the only sentinel. No `GroupEnd` or
`BranchSkip` is used: branches are mutually exclusive, and the 13 result ports re-converge
only at the `results-summary` sink (spec [10d](specs/10d-summarise-results.md)) via the `any`
contract's fan-in — not through a keyed join. The test graph's contracts are `unit` /
`default` / `keyed_join` / `any` (the last fanning the terminals into `results-summary`); there
is no `merge` contract.
