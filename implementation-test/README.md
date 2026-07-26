# Plan: the `test` command as an rtl-comrade graph

This directory is an **implementation plan**, not code. It describes how to re-build
the functionality of `rtl_buddy`'s `test` command (see `rtl_buddy/`) as an
`rtl-comrade` graph of atomic, reusable modules scheduled by contracts.

Read in order:

- [00-overview.md](00-overview.md) — goal, design philosophy, the end-to-end dataflow at a glance. Its Mermaid flowchart renders to `dataflow-diagram.svg`; re-run the repo-root [`regen-dataflow-diagram.sh`](../regen-dataflow-diagram.sh) `implementation-test` (uses `mmdc`, falling back to `npx @mermaid-js/mermaid-cli`) after editing the diagram.
- [01-cli-and-entry.md](01-cli-and-entry.md) — how the `test` CLI surface maps onto CLI edges + the config-file command entry
- [02-payload-conventions.md](02-payload-conventions.md) — the split per-test/per-run keyed edges, branch payloads, and the correlation key
- [03-module-catalog.md](03-module-catalog.md) — every atomic module: signature, config, output ports, paired contract, tags, reuse notes
- [04-pipeline-and-contracts.md](04-pipeline-and-contracts.md) — the node graph, stage ordering, contract choice per node, fan-out/persistent wiring
- [05-branching-and-results.md](05-branching-and-results.md) — early-stop / compile-fail / sim-timeout / skip / post routing, result aggregation, exit-code mapping
- [06-graph-yaml.md](06-graph-yaml.md) — a concrete proposed `graphs/test.yaml` plus manifest additions
- [07-ambiguities-and-assumptions.md](07-ambiguities-and-assumptions.md) — every assumption, judgement call, and open question for you to confirm
- [08-sibling-graphs.md](08-sibling-graphs.md) — `randtest` and `regression` graphs: new modules, reuse, and structural concerns

The framework this plan targets is documented under `docs/` (modules, contracts,
harness, configs). This plan was written from a fresh trace of `rtl_buddy/` and the
`rtl-comrade` docs only; it does **not** reference any pre-existing graph or plan for
the `test` command.
