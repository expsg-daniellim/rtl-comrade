# Divergences from rtl_buddy

Behavioural deltas discovered or confirmed during end-to-end validation (spec 12).
Each entry notes whether the delta is deliberate (per the design plan in
`implementation-test/07-ambiguities-and-assumptions.md`) or an unexpected finding.

---

## Deliberate divergences (anticipated by [07])

These are documented in [07 — Notable divergences](implementation-test/07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy) and are expected.

### `--early-stop` exits 0 instead of 1

rtl_buddy exits 1 on `--early-stop` because it treats an NA verdict as a failure
(`EarlyStopResults.is_pass()` returns False). rtl-comrade treats a user-requested
early stop as a deliberate, successful early exit: `early-stop-gate` emits no
`log.error`, so the run exits 0. The per-test NA verdict is unchanged.

### `--early-stop pre/comp` desc uses phase token

rtl_buddy emits `"Stopped early at preproc"` / `"Stopped early at compile"` for the
`pre` and `comp` phases. rtl-comrade emits `"Stopped early at pre"` / `"Stopped
early at comp"` (the phase token). The `sim` desc is identical between the two.

### Compile logs persisted to files

rtl_buddy captures compile output in memory (`subprocess.run(capture_output=True)`)
and logs it on failure but never writes it to disk. rtl-comrade redirects compile
stdout/stderr to `logs/<test>.compile.log` / `logs/<test>.compile.err` as a side
effect of `run-process` always redirecting. The files are produced even on success.

### `load-model` is lazy

rtl_buddy loads every test's model during suite parsing (`TestConfigFile.initialise`),
so a broken `models.yaml` on a skipped test causes an early error. rtl-comrade loads
models lazily, per-test, after `filter-reglvl` has excluded skipped tests. A broken
`models.yaml` on a filtered-out test is never read and does not affect the run.

### `ParseLogMod` corrects VlogPost quirks

rtl_buddy's `VlogPost` has three bugs corrected in `ParseLogMod`:
1. Word-boundary guard: `PASSTHROUGH` no longer misclassifies as PASS.
2. FAIL wins over PASS when both appear in the log.
3. FAIL-without-`ERR:` no longer crashes (`AttributeError` on `None.group(2)`).

### `select-platform` is first-match

rtl_buddy's `config/root.py` iterates all platforms with no `break`, so the last
matching platform wins when two share a `uname`. rtl-comrade returns on the first
match. Overlapping `unames` are a misconfiguration; single-platform-per-`uname`
configs (the norm) are unaffected.

### `-L/--logs-dir` override and centralised artefact provenance

rtl_buddy hard-codes `"logs"` as the artefact subdirectory. rtl-comrade accepts a
`-L/--logs-dir` CLI override (default `"logs"`) and centralises artefact-location
provenance in the `work-dir` and `ensure-logs-dir` nodes.

---

## Fixed-simv concurrency hole (deferred, [07 item 17])

On non-verilator (fixed-simv) builders, a concurrent multi-test run can overwrite one
test's binary with another's and silently report wrong results (rc 0, green summary).
There is no built-in serialisation. This is an expected, known limitation deferred
until the upstream rtl_buddy per-invocation-subdir change lands. Validate fixed-simv
builders one test per invocation as an operational workaround.

Verilator builders are unaffected: each test writes to a per-tag `obj_dir_<tag>/`
directory, so concurrent runs do not collide.
