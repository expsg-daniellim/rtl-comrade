# Sibling graphs: `randtest` and `regression`

Both sibling commands funnel into the same core as `test` (`_do_test_suite` →
`_run_test_cfg_for_run_ids` → `TestRunner` → `VlogSim`), so the module catalogue from
[03](03-module-catalog.md) carries over almost entirely. Only the CLI surface and a few
orchestration nodes differ.

## Reused unchanged

The entire main pipeline carries over with the same contracts and wiring:

- setup chain — `discover-config-file`, `prepend-cwd-path` *(wired to both `run-process`
  instances via `env_ready` in every graph — see [07 settled
  25](07-ambiguities-and-assumptions.md))*, `parse-root-config`, `select-platform`,
  `resolve-builder`, `check-suite-cwd` *(test/randtest only — regression chdir's per-suite,
  see structural note #1)*, `parse-suite-config` *(contract switches for regression — see
  below)*, `load-model`
- selection / expansion — `route-list-mode`, `list-test-names`, `select-tests`,
  `filter-reglvl` *(finally exercised by regression)*, `expand-sweep`, `run-preproc`
- per-test — `gate-pre`, `write-filelist`, `build-compile-cmd`, `run-process` (compile),
  `interpret-compile`, `gate-comp`
- per-run — `expand-runs`, `resolve-seed`, `build-sim-cmd`, `run-process` (sim),
  `write-randseed`, `link-latest`, `interpret-sim`, `gate-sim`
- post — `route-post`, `parse-log`, `parse-uvm-log`
- control — `early-stop-gate`
- summary — the `SummaryProcessor` logging plugin (per TODO #15 item 27; replaces the former
  `fan-in-results` + `aggregate-results` + `any` fan-in). Sibling graphs reuse it by carrying
  the same `logging` block.

---

## `randtest` graph

`randtest` differs from `test` only in seed handling: `--rnd-rpt i` → REPLAY of run-id `i`;
otherwise NEW seeds across `[1..rnd_cnt]`.

### CLI surface (matching rtl_buddy)

| arg | flag / position | type | default |
|---|---|---|---|
| `test_name` | positional (**required**) | str | — |
| `rnd_cnt` | positional | int | 2 |
| `rnd_rpt` | `-r/--rnd-rpt` | int | -1 (sentinel "not given") |
| `test_config` | `-c/--test-config` | str | `tests.yaml` |
| `builder`, `builder_mode`, `early_stop` | same as `test` | | |

(Note: rtl_buddy uses `rnd_rpt = None` as the absent sentinel; the harness's primitive-only
CLI edges use `-1` instead — `derive-randtest-runs` treats negative as absent.)

### New module

#### `derive-randtest-runs`  · tags: setup · contract: `unit`
Collapses the randtest CLI into the two values downstream needs.

- **In:** `rnd_cnt:int = 2`, `rnd_rpt:int = -1`
- **Out:** `("run_ids", list[int])`, `("seed_mode", SeedMode)`
- **Semantics:**
  - `rnd_rpt >= 0` → `run_ids = [rnd_rpt]`, `seed_mode = REPLAY`
  - else → `run_ids = list(range(1, rnd_cnt + 1))`, `seed_mode = NEW`

`run_ids` is emitted as a single `list[int]` payload because it is *config* (a fixed,
small, startup-known set) — `expand-runs` is the streaming fan-out point that turns one
compiled test into N concurrent run-items downstream. See the design note at the end of
this file.

### Wiring (delta vs `test` graph)

- `derive-randtest-runs` **replaces** `derive-seed-mode`.
- `derive-randtest-runs.run_ids` → `expand-runs.run_ids` (persistent).
- `derive-randtest-runs.seed_mode` → `resolve-seed.seed_mode` (persistent).
- CLI edges: `rnd_new`/`rnd_last` removed; `rnd_cnt`, `rnd_rpt` added; `test_name` becomes
  a true required positional (no `default`); `--list` removed (randtest has no list mode).
- `check-suite-cwd` wired identically to the test graph (same user-driven CWD posture —
  see [01](01-cli-and-entry.md) and [07 settled 24](07-ambiguities-and-assumptions.md)).
- Everything else identical.

---

## `regression` graph

`regression` iterates over multiple suites (a `RegConfig`), each in its own working
directory, with level filtering. This is the bigger structural change.

### CLI surface (matching rtl_buddy)

| arg | flag | type | default |
|---|---|---|---|
| `reg_config` | `-c/--reg-config` | str | `""` (= derive from root cfg) |
| `reg_level` | `-l/--reg-level` | int | 0 |
| `start_level` | `-s/--start-level` | int | 0 |
| `builder`, `early_stop` | same as `test` | | |
| `builder_mode` | `-M/--builder-mode` | str | **`"reg"`** (overridden default) |

No `test_name`, `list`, `rnd_new`, `rnd_last`.

### New modules

#### `parse-reg-config`  · tags: setup · contract: `unit` (fan-out)
Deserialise `regressions.yaml` (schema preserved: `rtl-buddy-filetype: reg_config`,
`test-configs: list[str]`) and yield one suite path per `test-configs` entry.

- **In:** `reg_config_path:Path`
- **Out:** default → `Path` per suite (generator: 1 → N)

#### `resolve-reg-config-path`  · tags: setup · contract: `unit`
Bridge the CLI default to rtl_buddy's behaviour: if the `reg_config` CLI is empty, pull the
path from `root_cfg.cfg-rtl-reg.reg-cfg-path`; else use the CLI value as-is. Atomic so the
default-resolution lives in one obvious place.

- **In:** `reg_config:str = ""`, `root_cfg` (persistent)
- **Out:** default → `Path`

### Reused with a different contract

- **`parse-suite-config`** — switches from `unit` (test/randtest) to `default` (regression),
  because there are now N suites to parse, one per item arriving on its input port. This is
  a per-graph node-config choice, not a module change.

### Wiring (delta vs `test` graph)

- Suite stream: `resolve-reg-config-path` → `parse-reg-config` → `parse-suite-config` →
  `select` directly (regression has no list mode — drop `route-list`/`list-names` from
  this graph). `check-suite-cwd` is **not** wired: regression `chdir`s per-suite (see
  structural note #1), so each `parse-suite-config` invocation already sees the correct
  CWD without an upstream check.
- Filter wiring: `reg_level`/`start_level` CLI edges connect to the existing
  `filter-reglvl` persistent inputs (which sit unwired in the test graph).
- Suite stamping: `parse-suite-config` stamps the suite name into each test's identity
  early, so the correlation key becomes `<suite>/<test>#<sweep>#<run>`. The `SummaryProcessor`
  plugin (TODO #15 item 27) then needs no code change to produce per-suite-grouped output —
  every `test_result` row already carries the suite-prefixed key.
- `derive-seed-mode` removed; `resolve-seed` receives `seed_mode = DEFAULT` from a small
  constant emitter, *or* takes `seed_mode` as node config rather than a port. (Minor
  decision; either works.)
- Otherwise identical pipeline.

---

## Structural notes

1. **CWD chdir — resolved by the upstream rtl_buddy change.** Once each compile/sim runs
   in its own subdirectory ([07](07-ambiguities-and-assumptions.md) item 17), regression no
   longer needs to chdir per suite at all: subprocesses set up their own working dirs, and
   suite-relative paths (model paths, filelists) are resolved to absolute paths during
   parse. **`chdir-suite` is therefore dropped from the design below**, on the assumption
   that the upstream change lands before this is implemented. If for any reason the
   regression graph must be built before that upstream change, reinstate `chdir-suite` and
   add a serialising contract to enforce sequential suite processing.

2. **Summary aggregation matches rtl_buddy exactly with no extra work.** rtl_buddy's
   `do_rtl_regression` (`rtl_buddy.py:371-438`) collects every (suite, test) result across
   all suites and at lines 423-435 prints a **single end-of-run table** with `suite_name`
   as the first column (one row per `(suite, test)` pair), via `logger.result(...)`.
   `SummaryProcessor.finalise()` already does exactly this — one-shot summarisation at
   run end — and with the suite name stamped into the correlation key at
   `parse-suite-config` (`<suite>/<test>#<sweep>#<run>`), every row carries its suite, the
   summary table groups naturally on that prefix, and the OR-accumulated exit code falls
   out the same way. **No module change needed.**

3. **`parse-suite-config` contract switch — elaboration.** The module's behaviour ("read
   a YAML at this path, emit a `SuiteConfig`") is identical in both graphs. Only the
   *cadence* differs:

   - In the `test`/`randtest` graph, the node sits behind a single CLI string (the
     `test_config` edge) and must run **exactly once** → pair the node with **`unit`**.
   - In the `regression` graph, the node sits behind a **stream of `Path`s** coming from
     `parse-reg-config` (one per `test-configs` entry in `regressions.yaml`) and must run
     **once per suite** → pair the node with **`default`**.

   This is purely a per-node graph-YAML decision (the `contract:` field on the node
   definition); the module class is unchanged. The harness's separation of concerns
   between modules and contracts is exactly what makes this possible — `unit` and `default`
   both deliver one dict-of-inputs per invocation in the same shape the module expects, so
   the module is contract-agnostic. The wiring on the input side is what changes: in test,
   the `test_config_path` port is fed by `check-suite-cwd`'s resolved path; in regression, it's
   fed by `parse-reg-config`'s default output. The module doesn't care which.

   Build-time verification points: confirm the harness handles the `test_config_path` port
   receiving a resolved `Path` from a `unit` upstream (`check-suite-cwd`) in test and from a
   `default` upstream (`parse-reg-config`, one per suite) in regression — the same `Path`
   payload the module parses either way; and confirm that the
   `EndSentinel` propagation from a `default`-contract `parse-suite-config` correctly drains
   the downstream pipeline at end-of-stream (it will, because `default` returns
   `EndSentinel` when its required port ends, which cascades through the rest).

---

## Summary

- **randtest:** 1 new module (`derive-randtest-runs`); CLI rewiring only.
- **regression:** 2 new modules (`parse-reg-config`, `resolve-reg-config-path`) + 1
  contract switch (`parse-suite-config`: unit → default) + CLI rewiring. (`chdir-suite`
  was originally listed but is dropped — see structural note #1.)
- **No new contract types** beyond those already in the test graph (`unit` / `default` /
  `keyed_join`, plus an unwired `any`).
- **Most of the module catalogue** ([03](03-module-catalog.md)) is reused untouched.

---

## Design note — `derive-randtest-runs` emitting `list[int]`

A natural objection: emitting a list as one payload doesn't seem to take advantage of the
graph's streaming execution. The answer hinges on whether the list is *config* or *stream*:

- `run_ids` is **config** here — a fixed, startup-known set with a small cardinality
  (typically a single-digit `rnd_cnt`). The "streaming" question doesn't really apply to
  startup config.
- The actual streaming/fan-out happens **downstream at `expand-runs`** — that node is a
  generator: one compiled-test `ctx` in, `N` per-run `ctx`s out, each immediately available
  to the sim pipeline as it is yielded. Multiple compiled tests' run-expansions interleave
  naturally with each other and with subsequent sims.
- Emitting individual `int`s from `derive-randtest-runs` would require `expand-runs` to
  *buffer* the full set before fanning out any test (it needs to know `N` per test), or
  would require a new "cartesian product" contract pairing the ctx stream with a run-id
  stream. Neither improves throughput for fixed small `N`; both add machinery.

If, in a future where `rnd_cnt` could be unbounded, this trade-off shifts — drop
`derive-randtest-runs` entirely and have `expand-runs` take `rnd_cnt`/`rnd_rpt` directly
as persistent config (computing `run_ids` lazily inside its own generator).
