# Branch-Awareness (Control-Dependence Labelling)

Sources: [src/rtl_comrade/structure.py](../../src/rtl_comrade/structure.py), [src/rtl_comrade/graph.py](../../src/rtl_comrade/graph.py), [src/rtl_comrade/contract_default.py](../../src/rtl_comrade/contract_default.py)

## Why

A contract that awaits several input ports assumes they belong to one synchronised stream: if some end while others carry data, that is a desync error. But a node's inputs can come from streams with independent termination lifetimes — an upstream branch ends one while another stays live. Without knowing the graph's branch structure, a contract cannot tell a legitimate branch outcome from a real desync, and flags the former as an error.

Branch-awareness gives every input port a **control-dependence label** so contracts can distinguish the two.

## Concepts

- A **branch origin** is a node that does not emit all its output ports on every invocation.
- An **arm** is one alternative group of an origin's outputs — the set of ports sharing a guarding branch-path. Arm identity is `(origin_node_id, frozenset(arm_port_names))`.
- Two arms are **mutually exclusive** when at most one of them is ever selected. This is a pairwise relation over their guarding paths, not a property of being distinct arms: `if`/`else` and `match`-case siblings qualify, two independent `if`s do not. It is also not transitive, so it cannot be reduced to a grouping of arms.
- A port's **`branch_labels`** (`frozenset`, on `ContractPort`) is the set of arms whose non-selection can end that port's stream. Two ports are **co-fated** iff their label sets are equal.

## Determination — `structure.py`

`ModuleStructure` computes the arm partition over a module's statically-named output ports by their guarding branch-path (`if`/`else`, `match` cases → distinct arms; a loop body → one conditional arm; `try`/`except` → each emit is its own optional arm; ports emitted unconditionally or under several guards belong to no arm). This is a single structured pass that also yields `emits` and `definite_emits`. Each arm keeps its guarding path in `arm_paths`, which is what `exclusive_arms` reads: two arms are mutually exclusive when neither path is a prefix of the other and the first element they differ at names the same branching statement. So `try` sections, loop bodies, and separate `if`s never qualify, which is conservative — it can refuse a merge that is in fact safe, never permit one that is not.

Dynamic emitters (`**kwargs`, computed port names) cannot be named by the AST. They declare a class attribute `output_groups`, a mapping of group name to member ports where a `REST` member list (from `rtl_comrade.api`) means "all outputs not named in another group".

`resolve_arms` combines the two (see the matrix in [structure.md](structure.md)): AST-only when definite and undeclared; declaration-fills-dynamic when non-definite; and a fatal cross-check when a declaration contradicts what the AST could prove. A non-definite emitter with no declaration warns and falls back to one shared arm. It reports which of the two it returned, because a declaration is an assertion that its groups are alternatives — declared arms are mutually exclusive by construction, since the AST cannot cross-check ports it could not name.

## Propagation — `graph.py`

The label-propagation pass in `Graph.from_config` runs after edge wiring (the graph is already validated acyclic) and walks nodes in topological order. Each output port's label is the union of its node's **gating** input labels plus a `(node_id, arm)` term when the port belongs to an arm. An input **gates** production iff the node cannot produce its first output without it — `not (has_default and not required)`, the same predicate as `is_special` at first run. Non-gating inputs (default-valued, omittable) do not propagate. It returns an `input_labels` map (`dict[node_id, dict[port_name, frozenset]]`); no `Port` is mutated. The labels are injected into the `ContractPort`s at `Node.from_prenode`, so each contract owns its ports with their labels already set.

An input port collects one label per incoming edge and is labelled by their **intersection**: an arm can end the port only if every one of its sources depends on that arm, since any source that does not keeps feeding it. Two exclusive arms of one origin therefore cancel each other out and leave the inherited prefix, which is right — one of them always fires. Indegree reaching zero is what guarantees a node's edge labels are complete, so the fold happens as each node is dequeued.

That same point is where multi-source ports are validated: every pair of edge labels must be ruled out by some arm of a common origin, or the port is reported in `overloaded_srcs`. Doing it here rather than in `validation.py` is deliberate — the check is the labels, so it cannot run before they exist.

## Consumption — `contract_default.py`

`DefaultContract` partitions its awaited ports by `branch_labels` and logs `mismatched_end` only within a partition that holds both a data port and an ended port. Divergence across partitions is a branch legitimately ending one arm and is not an error. Termination is unchanged: any awaited end still returns `EndSentinel`. Other contracts may read `ContractPort.branch_labels` to make the same distinction.

## See Also

- [structure.md](structure.md) — arm determination and the `output_groups` matrix
- [graph.md](graph.md) — the propagation pass
- [contract_default.md](contract_default.md) — the relaxed mismatch check
- [api.md](api.md) — `ContractPort.branch_labels`, `REST`
