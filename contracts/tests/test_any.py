"""Tests for AnyContract."""

import asyncio
import collections
import random

import pytest
import typer

from rtl_comrade.api import Payload, EndSentinel, ContractPort
from rtl_comrade.port import Port
from rtl_comrade.testing import run_contract_scenario, PortTestInput

from contracts.any import AnyContract

END = EndSentinel("src")


def _make_contract_ports(ports:dict[str, Port]) -> dict[str, ContractPort]:
	return {
		name: ContractPort(name=name, get=port.get, try_get=port.try_get, has_ended=port.has_ended, has_default=port.has_default, required=False)
		for name, port in ports.items()
	}


# ── Behavioural cases — default n→1 ────────────────────────────────────────

async def test_single_item_one_port_active():
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [1, END], "b": [END], "c": [END]},
		expected_outputs=[{"default": 1}, END],
	)


async def test_three_ports_all_deliver():
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [1, END], "b": [2, END], "c": [3, END]},
		expected_outputs=[{"default": 1}, {"default": 2}, {"default": 3}, END],
	)


async def test_early_end_on_one_port():
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [END], "b": [2, END], "c": [3, END]},
		expected_outputs=[{"default": 2}, {"default": 3}, END],
	)


async def test_all_ports_ended_immediately():
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [END], "b": [END], "c": [END]},
		expected_outputs=[END],
	)


async def test_no_loss_simultaneous_completion():
	# Both ports are pre-loaded and complete in the same asyncio.wait wake-up;
	# the contract must return exactly one dict per call and not lose the other.
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [1, END], "b": [2, END]},
		expected_outputs=[{"default": 1}, {"default": 2}, END],
	)


async def test_drainage_fifo():
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [10, 20, END], "b": [END], "c": [END]},
		expected_outputs=[{"default": 10}, {"default": 20}, END],
	)


async def test_pending_task_skipped_when_not_done():
	# Port "a" (inserted first) has nothing queued while port "b" already holds an item,
	# so the first asyncio.wait wake finds "b" done and "a" still pending. Iterating
	# pending in insertion order reaches "a" first and skips it (task not in done) — the
	# branch a same-tick completion of every task never reaches.
	ports = {"a": Port(name="a"), "b": Port(name="b")}
	contract = AnyContract(id="skip", ports=_make_contract_ports(ports))
	ports["b"].queue.put_nowait(Payload(source="test", n=0, payload=2))
	assert (await contract.get_inputs())["default"].payload == 2
	# Drain "a" and both ends to a clean termination.
	ports["a"].queue.put_nowait(Payload(source="test", n=0, payload=1))
	ports["a"].queue.put_nowait(END)
	ports["b"].queue.put_nowait(END)
	assert (await contract.get_inputs())["default"].payload == 1
	assert isinstance(await contract.get_inputs(), EndSentinel)


async def test_blocking_await():
	# Port a ends immediately; port b delivers its payload after one event loop yield,
	# exercising the await asyncio.wait branch that blocks until an item arrives.
	await run_contract_scenario(
		AnyContract,
		port_inputs={
			"a": [END],
			"b": [PortTestInput(9, delay=1), PortTestInput(END, delay=2)],
		},
		expected_outputs=[{"default": 9}, END],
	)


# ── Behavioural cases — configured output ──────────────────────────────────

async def test_named_n_to_1_output():
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [1, END], "b": [2, END]},
		expected_outputs=[{"merged": 1}, {"merged": 2}, END],
		config=AnyContract.Config(mapping="merged"),
	)


async def test_m_to_n_grouping():
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [1, END], "b": [2, END], "c": [3, END]},
		expected_outputs=[{"x": 1}, {"x": 2}, {"y": 3}, END],
		config=AnyContract.Config(mapping={"x": ["a", "b"], "y": ["c"]}),
	)


# ── Construction-time tests ─────────────────────────────────────────────────

async def test_default_config_omitted():
	# Omitting contract_config defaults to n→1 onto "default".
	await run_contract_scenario(
		AnyContract,
		port_inputs={"a": [1, END], "b": [END]},
		expected_outputs=[{"default": 1}, END],
	)


async def test_unknown_input_port_is_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		await run_contract_scenario(
			AnyContract,
			port_inputs={"a": [END], "b": [END], "c": [END]},
			expected_outputs=[],
			config=AnyContract.Config(mapping={"x": ["nope"]}),
		)


async def test_ambiguous_output_mapping_is_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		await run_contract_scenario(
			AnyContract,
			port_inputs={"a": [END], "b": [END], "c": [END]},
			expected_outputs=[],
			config=AnyContract.Config(mapping={"x": ["a"], "y": ["a"]}),
		)


async def test_unmapped_input_port_is_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		await run_contract_scenario(
			AnyContract,
			port_inputs={"a": [END], "b": [END], "c": [END]},
			expected_outputs=[],
			config=AnyContract.Config(mapping={"x": ["a", "b"]}),
		)


# ── Stress tests ────────────────────────────────────────────────────────────

_N_STRESS_PORTS = 13
_N_STRESS_ITEMS = 100

# Partition for the dict-mapping stress test: 13 ports across 3 output groups.
_STRESS_PARTITION = {
	"out0": [f"p{i}" for i in range(5)],
	"out1": [f"p{i}" for i in range(5, 9)],
	"out2": [f"p{i}" for i in range(9, 13)],
}


async def _stress_feeder(port:Port, n:int, seed:int) -> None:
	rng = random.Random(seed)
	for i in range(n):
		if rng.random() < 0.5:
			await asyncio.sleep(0)
		port.queue.put_nowait(Payload(source="feeder", n=i, payload=(port.name, i)))
	port.queue.put_nowait(EndSentinel("feeder"))


async def _collect_stress_results(contract:AnyContract, total_expected:int) -> list[tuple[str, tuple]]:
	delivered = []
	while True:
		res = await asyncio.wait_for(contract.get_inputs(), timeout=30.0)
		if isinstance(res, EndSentinel):
			break
		[(output, payload)] = res.items()
		delivered.append((output, payload.payload))
	assert len(delivered) == total_expected
	return delivered


async def test_stress_n_to_1():
	port_names = [f"p{i}" for i in range(_N_STRESS_PORTS)]
	ports = {name: Port(name=name) for name in port_names}
	contract = AnyContract(id="stress", ports=_make_contract_ports(ports))
	feeders = [ asyncio.create_task(_stress_feeder(ports[name], _N_STRESS_ITEMS, i)) for i, name in enumerate(port_names) ]
	delivered = await _collect_stress_results(contract, _N_STRESS_PORTS * _N_STRESS_ITEMS)
	for t in feeders:
		await t
	assert all(output == "default" for output, _ in delivered)
	assert collections.Counter(payload for _, payload in delivered) == collections.Counter(
		(f"p{i}", j) for i in range(_N_STRESS_PORTS) for j in range(_N_STRESS_ITEMS)
	)


async def test_stress_dict_mapping():
	port_names = [name for names in _STRESS_PARTITION.values() for name in names]
	ports = {name: Port(name=name) for name in port_names}
	contract = AnyContract(id="stress_dict", ports=_make_contract_ports(ports), config=AnyContract.Config(mapping=_STRESS_PARTITION))
	feeders = [ asyncio.create_task(_stress_feeder(ports[name], _N_STRESS_ITEMS, i)) for i, name in enumerate(port_names) ]
	delivered = await _collect_stress_results(contract, _N_STRESS_PORTS * _N_STRESS_ITEMS)
	for t in feeders:
		await t
	port_to_output = {name: out for out, names in _STRESS_PARTITION.items() for name in names}
	by_output:dict[str, list] = collections.defaultdict(list)
	for output, payload in delivered:
		by_output[output].append(payload)
	for out, group_names in _STRESS_PARTITION.items():
		expected = collections.Counter((name, i) for name in group_names for i in range(_N_STRESS_ITEMS))
		assert collections.Counter(by_output[out]) == expected, f"mismatch on output {out!r}"
	_ = port_to_output  # used above; keep reference to suppress linter


# ── Property-based test ─────────────────────────────────────────────────────

@pytest.mark.parametrize("seed", range(100))
async def test_property_based(seed:int):
	rng = random.Random(seed)
	port_count = rng.randint(2, 7)
	items_per_port = rng.randint(1, 15)
	port_names = [f"q{i}" for i in range(port_count)]

	# Randomly decide n→1 or m→n.
	if rng.random() < 0.5:
		output_name = rng.choice(["default", "out", "result"])
		mapping:str | dict[str, list[str]] = output_name
		port_to_output = {name: output_name for name in port_names}
	else:
		n_groups = rng.randint(1, port_count)
		groups:dict[str, list[str]] = {f"g{i}": [] for i in range(n_groups)}
		shuffled = port_names[:]
		rng.shuffle(shuffled)
		# Seed each group with at least one port to avoid empty groups.
		group_keys = list(groups.keys())
		for idx, name in enumerate(shuffled[:n_groups]):
			groups[group_keys[idx]].append(name)
		for name in shuffled[n_groups:]:
			groups[rng.choice(group_keys)].append(name)
		mapping = groups
		port_to_output = {name: g for g, names in groups.items() for name in names}

	ports = {name: Port(name=name) for name in port_names}
	# Pre-enqueue all items and end sentinels.
	for i, name in enumerate(port_names):
		for j in range(items_per_port):
			ports[name].queue.put_nowait(Payload(source="test", n=j, payload=(name, j)))
		ports[name].queue.put_nowait(EndSentinel("test"))

	contract = AnyContract(id="prop", ports=_make_contract_ports(ports), config=AnyContract.Config(mapping=mapping))

	delivered:list[tuple[str, tuple]] = []
	while True:
		res = await asyncio.wait_for(contract.get_inputs(), timeout=10.0)
		if isinstance(res, EndSentinel):
			break
		[(output, payload)] = res.items()
		delivered.append((output, payload.payload))

	expected = collections.Counter((port_to_output[name], (name, j)) for name in port_names for j in range(items_per_port))
	assert collections.Counter(delivered) == expected
