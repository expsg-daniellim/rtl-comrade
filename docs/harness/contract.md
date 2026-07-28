# `contract.py`

Source: [src/rtl_comrade/contract.py](../../src/rtl_comrade/contract.py)

## Role

This file resolves a config node's contract names into constructed contract objects. It owns the rule that a contract wraps **both** ends of a module — supplying inputs and processing outputs — and the rule that either end may be overridden independently.

## See Also

- [README.md](README.md)
- [graph.md](graph.md) — calls `ContractDefinitions.from_config` per node
- [node.md](node.md) — calls `ContractDefinitions.construct` and invokes the results
- [config.md](config.md) — the `GraphConfigNode` contract fields being resolved
- [api.md](api.md) — `ContractPort`, the surface handed to every constructed contract
- [contract_default.md](contract_default.md)
- [../contracts/implementation.md](../contracts/implementation.md) — the contract-author view of the same model

## Main Responsibilities

- resolve each of a node's `contract` / `input_contract` / `output_contract` names against the loaded contract plugins
- check each resolved class exposes the callable its role requires, and that `process_outputs` has a usable signature
- build the node's `ContractPort` surface once and construct every defined contract against it
- carry the contract config dict through serde deserialisation and `{graph}` path relativisation at construction time

## Place In The System

`contract.py` sits between `graph.py` (which knows names) and `node.py` (which knows ports). Contract resolution used to be split across both: `graph.py` checked every loaded contract had `get_inputs`, and `Node.from_prenode` did the signature inspection and construction inline. Both now delegate here.

The split is deliberate: `ContractDefinition.from_config` runs during graph assembly, when only plugin names exist, so a bad contract name or a contract missing its required method is rejected before any node runs. `ContractDefinition.construct` runs later, in `Node.from_prenode`, once each port's control-dependence labels are known.

## Main Types

- `ContractDefinition[T]` — one resolved contract class, its config dict, and the role it fills (`type_`). Produced by `from_config`, consumed by `construct`.
- `ContractDefinitions[C, IC, OC]` — a node's three contract slots fully unravelled. `contract` is always present; `input_contract` and `output_contract` are `None` when that end is not overridden.
- `MissingContractError`, `MissingContractFunctionError`, `MissingContractParameterError`, `InvalidContractParameterTypeError` — resolution failures, raised out of `from_config` and turned into `ERROR` logs by `graph.py`.

## Role Resolution

A node has three contract fields; `ContractDefinitions` reduces them to what each end will actually use:

| Field | Role | Unset (`""`) behaviour |
|---|---|---|
| `contract` | serves whichever end is not overridden | resolves to the built-in `DefaultContract` |
| `input_contract` | overrides `contract` for `get_inputs` | `None` — the input end falls to `contract` |
| `output_contract` | overrides `contract` for `process_outputs` | `None` — the output end falls to `contract`, but only if `contract` defines `process_outputs` |

The consequence worth internalising: a general `contract` is required to expose `get_inputs`, but `process_outputs` is optional on it. A node with only `contract: zip` therefore does no output processing at all — outputs go straight downstream. Output processing is opt-in, either by naming an `output_contract` or by giving the general contract a `process_outputs`.

Setting all three fields makes `contract` unreachable: both ends are overridden and nothing is left for it to serve. `graph.py` warns `obsolete_contract` for this rather than failing, since the config is harmless.

## Interface Checks

`from_config` validates per role, so a contract is only held to the interface it will actually be asked for:

- an `input_contract` (and a general `contract`) must expose a callable `get_inputs` — otherwise `MissingContractFunctionError`
- an `output_contract` must expose a callable `process_outputs` — otherwise `MissingContractFunctionError`
- `process_outputs` is signature-checked whenever it will be used: always for an `output_contract`, and for a general `contract` only when it defines one. It must declare `port` and `value` (`MissingContractParameterError` otherwise), and `port` must be annotated `str` or left unannotated (`InvalidContractParameterTypeError` otherwise)

These checks are per-node and per-role. A contract plugin that only makes sense on the output end no longer has to carry a stub `get_inputs` to survive loading — the previous global "every loaded contract has `get_inputs`" screen in `graph.py` is gone.

## Construction

`ContractDefinitions.construct(node_id, ports, input_labels, required_ports, relative_path)` builds the `ContractPort` adapters **once** and passes the same mapping to every contract the node defines. A node's input and output contracts therefore observe the same per-port `state` dicts, which is how an output contract can react to what the input contract consumed.

`ContractDefinition.construct` then injects only the constructor arguments each class declares, unchanged from the previous `Node.from_prenode` behaviour:

- `config` → the role's config dict, deserialised through the contract's nested `Config` when it has one, with `{graph}`-prefixed `Path` fields resolved against `relative_path`
- `id` → `<node-id>.contract`
- `ports` → the shared `ContractPort` mapping

An input-side contract that does not declare `ports` gets an `init.no_ports` warning — it has nothing to read. An output contract that omits `ports` is unremarkable and is not warned about, since `process_outputs` receives its value as an argument.

## Caveats

- every constructed contract on a node shares one `ContractPort` mapping, so contracts that both write `port.state` under the same key will clobber each other; that sharing is the intended channel between them, not an accident
- an output contract receives `ports` when it asks for them, but cannot read from them: reads are disabled outside `get_inputs`, so `get()`/`try_get()` raise `IllegalGetAccessError`. See [port.md](port.md)
- the `id` injected is `<node-id>.contract` for all three roles, so a node's input and output contracts log under the same id
- `from_config` raises rather than logging, so `graph.py` can attribute each failure to a node index and continue collecting errors across the rest of the graph; the fatal is deferred to the end of the node loop
