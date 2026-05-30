# Spec 00: Framework verification

**Depends on:** none.
**References:** [07 items 19, 21, 22](../07-ambiguities-and-assumptions.md).

## Goal

Empirically confirm the harness behaviours the design relies on, before any module is
written. A failure here means the design needs a small revision before building further.

## Deliverables

Throw-away probe tests under `tests/probes/`:

- **`test_kwargs_port_inference.py`** — a minimal node module with `run(self, **kwargs)`;
  wire two edges into it under arbitrary port names; confirm the harness routes them.
  (Underwrites `aggregate-results` with the `merge` contract in spec 10.)
- **`test_persistent_no_edge.py`** — a node with `default` contract, listing a port in
  `persistent_inputs` that has no upstream edge, where the corresponding `run()` parameter
  has a Python default; confirm the module runs with the default. (Underwrites
  `filter-reglvl`'s `reg_level`/`start_level` in spec 05.)
- **`test_keyed_join_unwrap.py`** — pair two upstream nodes feeding one `keyed_join`
  downstream; confirm the dict payloads arrive in the downstream module unwrapped from
  `Payload`. (Underwrites `interpret-compile` and `write-randseed` in specs 07/08.)

## Acceptance criteria

- All three probes pass.
- If any fails: document the actual behaviour, update the relevant 07 item with the
  correction, and revise the affected design before starting the downstream spec.

## Notes

Probes are throw-away. Keep them minimal — the goal is to *learn*, not to ship. Run before
investing in modules so a wrong assumption doesn't cost rework.
