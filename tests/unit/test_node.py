"""Unit tests for node.py — PreNode construction, get_canonical_port, process_result, run."""

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from serde import SerdeError
from serde.compat import UserError

from rtl_comrade.api import Payload, EndSentinel
from rtl_comrade.config import GraphConfigNode, GraphConfigNodePlugin, GraphConfigEdge, GraphConfigSrcPort, GraphConfigDstPort
from rtl_comrade.contract import ContractDefinition, ContractDefinitions
from rtl_comrade.contract_default import DefaultContract
from rtl_comrade.module import GraphModule, PortInvalidMappingTarget, PortNonDefinitePositionalDestinationError
from rtl_comrade.node import Node, PreNode, InvalidNodeModule
from rtl_comrade.port import Port


# ---------------------------------------------------------------------------
# Minimal module/contract classes defined at module scope so inspect.getsource works
# ---------------------------------------------------------------------------


class _MinimalModule:
	def run(self):
		return None


class _ModuleWithConfig:
	def __init__(self, config):
		self.cfg = config

	def run(self):
		return None


class _ModuleWithConfigClass:
	from serde import serde as _serde  # pylint: disable=import-outside-toplevel

	@_serde  # pylint: disable=undefined-variable
	class Config:
		value: int = 0

	def __init__(self, config):
		self.cfg = config

	def run(self):
		return None


class _ModuleWithId:
	def __init__(self, id):  # pylint: disable=redefined-builtin
		self.given_id = id

	def run(self):
		return None


class _ModuleOneInput:
	def run(self, a):
		return a


class _ModuleTwoInputs:
	def run(self, a, b):
		return a + b


class _ModuleWithDefault:
	def run(self, a, b=10):
		return a + b


class _ModuleReturnDefault:
	def run(self):
		return 42


class _ModuleReturnNamed:
	def run(self):
		return ("out", 99)


class _SyncGenModule:
	def run(self):
		yield 1
		yield 2
		yield 3


class _AsyncModule:
	async def run(self):
		return 7


class _AsyncGenModule:
	async def run(self):
		yield 10
		yield 20


class _CrashModule:
	def run(self):
		raise ValueError("oops")


class _ModuleWithSyncFinalise:
	def __init__(self):
		self.finalise_called = False

	def run(self):
		return None

	def finalise(self):
		self.finalise_called = True


class _ModuleWithAsyncFinalise:
	def __init__(self):
		self.finalise_called = False

	def run(self):
		return None

	async def finalise(self):
		self.finalise_called = True


class _ModuleWithCrashingFinalise:
	def run(self):
		return None

	def finalise(self):
		raise RuntimeError("finalise crashed")


class _ModuleWithNonCallableFinalise:
	finalise = "not_a_function"

	def run(self):
		return None


class _ModuleWithFinalisePlainReturn:
	def run(self):
		return None

	def finalise(self):
		return 99


class _ModuleWithFinaliseNamedReturn:
	def run(self):
		return None

	def finalise(self):
		return ("out", 42)


class _ModuleWithFinaliseSyncGenerator:
	def run(self):
		return None

	def finalise(self):
		yield 1
		yield 2
		yield 3


class _ModuleWithFinaliseAsyncReturn:
	def run(self):
		return None

	async def finalise(self):
		return 77


class _ModuleWithFinaliseAsyncGenerator:
	def run(self):
		return None

	async def finalise(self):
		yield 10
		yield 20


class _ModuleInitExitModule:
	"""Module whose __init__ raises typer.Exit (simulates log.fatal inside init)."""
	def __init__(self):
		raise typer.Exit(1)

	def run(self):
		return None


class _NoPortsContract:
	def __init__(self, id):  # pylint: disable=redefined-builtin
		self.id = id

	async def get_inputs(self):
		return EndSentinel(self.id)


class _ContractInitExitContract:
	"""Contract whose __init__ raises typer.Exit (simulates log.fatal inside init)."""
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		raise typer.Exit(1)

	async def get_inputs(self):
		return EndSentinel("x")


class _ContractGetInputsExitContract:
	"""Contract whose get_inputs raises typer.Exit (simulates log.fatal inside get_inputs)."""
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id

	async def get_inputs(self):
		raise typer.Exit(1)


class _ModuleWithFinaliseExitModule:
	"""Module whose finalise raises typer.Exit (simulates log.fatal inside finalise)."""
	def run(self):
		return None

	def finalise(self):
		raise typer.Exit(1)


class DoubleOutputContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	def process_outputs(self, port:str, value):
		return value * 2


class AsyncSuffixOutputContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def process_outputs(self, port:str, value):
		return f"{value}:{port}"


class GeneralOutputContract:
	"""Serves both ends: terminates the node and rewrites its outputs."""

	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def get_inputs(self):
		return EndSentinel(self.id)

	def process_outputs(self, port:str, value):
		return value + 1


class PortReadingOutputContract:
	"""Reads an input port from process_outputs, which the read window forbids."""

	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	def process_outputs(self, port:str, value):
		return self.ports["a"].try_get()


class ExitOutputContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	def process_outputs(self, port:str, value):
		raise typer.Exit(1)


class CrashOutputContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	def process_outputs(self, port:str, value):
		raise RuntimeError("deliberate process_outputs crash")


# Module-scope: ModuleStructure calls inspect.getsource, so these must be top-level.
class _InvalidTupleModule:
	def run(self):
		return (1, 2, 3)  # three-element tuple → StructureInvalidTupleError


class _NonStrPortNameModule:
	def run(self):
		return (42, "value")  # non-string port name → StructureNonStrPortNameError


# Contract helpers for construction-error tests (no getsource needed).
class _ContractConfigNoClass:
	"""Accepts config but has no Config inner class — triggers config.mismatch warning."""

	def __init__(self, id, ports, config):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def get_inputs(self):
		return EndSentinel(self.id)


class _ContractInitCrash:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		raise RuntimeError("deliberate contract init crash")

	async def get_inputs(self):
		return EndSentinel("x")


class _CrashGetInputsContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def get_inputs(self):
		raise RuntimeError("deliberate crash in get_inputs")


class _ModuleWithPathConfig:
	from serde import serde as _serde  # pylint: disable=import-outside-toplevel

	@_serde  # pylint: disable=undefined-variable
	class Config:
		file: Path

	def __init__(self, config):
		self.cfg = config

	def run(self):
		return None


class _ContractWithPathConfig:
	from serde import serde as _serde  # pylint: disable=import-outside-toplevel

	@_serde  # pylint: disable=undefined-variable
	class Config:
		file: Path

	def __init__(self, id, ports, config):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports
		self.cfg = config

	async def get_inputs(self):
		return EndSentinel(self.id)


def _make_prenode(Module, config=None, Contract=None, contract_config=None, relative_path=Path(), output_contract=None):
	definition = ContractDefinition('contract', Contract if Contract is not None else DefaultContract, contract_config if contract_config is not None else {})
	output_definition = ContractDefinition('output_contract', output_contract, {}) if output_contract is not None else None
	return PreNode(
		id="test_node",
		module=GraphModule.from_module(Module),
		config=config if config is not None else {},
		contract_definitions=ContractDefinitions(definition, None, output_definition),
		relative_path=relative_path,
	)


def _make_node(Module, config=None, Contract=None, contract_config=None, relative_path=Path(), dsts=None, output_contract=None):
	pre = _make_prenode(Module, config, Contract, contract_config, relative_path, output_contract)
	return Node.from_prenode(pre, dsts if dsts is not None else {}, {})


# --- Initialization ---


def test_init_no_params(logging_handler):
	node = _make_node(_MinimalModule)
	assert node.id == "test_node"
	assert isinstance(node.module, _MinimalModule)


def test_init_config_no_config_class_warns(logging_handler):
	_make_node(_ModuleWithConfig, config={"x": 1})
	assert logging_handler.failure is False  # warn, not error


def test_init_config_with_config_class(logging_handler):
	node = _make_node(_ModuleWithConfigClass, config={"value": 7})
	assert node.module.cfg.value == 7


def test_init_graph_sentinel_path_resolved_against_relative_path(logging_handler, tmp_path):
	node = _make_node(_ModuleWithPathConfig, config={"file": "{graph}/data.txt"}, relative_path=tmp_path)
	assert node.module.cfg.file == tmp_path / "data.txt"


def test_init_absolute_path_config_not_modified_by_relative_path(logging_handler, tmp_path):
	abs_file = tmp_path / "data.txt"
	node = _make_node(_ModuleWithPathConfig, config={"file": str(abs_file)}, relative_path=Path("/some/other/dir"))
	assert node.module.cfg.file == abs_file


def test_init_relative_path_config_without_sentinel_not_modified(logging_handler, tmp_path):
	node = _make_node(_ModuleWithPathConfig, config={"file": "relative/path.txt"}, relative_path=tmp_path)
	assert node.module.cfg.file == Path("relative/path.txt")


def test_init_contract_graph_sentinel_path_resolved_against_relative_path(logging_handler, tmp_path):
	node = _make_node(_MinimalModule, Contract=_ContractWithPathConfig, contract_config={"file": "{graph}/data.txt"}, relative_path=tmp_path)
	assert node.contract.cfg.file == tmp_path / "data.txt"


def test_init_contract_absolute_path_config_not_modified_by_relative_path(logging_handler, tmp_path):
	abs_file = tmp_path / "data.txt"
	node = _make_node(_MinimalModule, Contract=_ContractWithPathConfig, contract_config={"file": str(abs_file)}, relative_path=Path("/some/other/dir"))
	assert node.contract.cfg.file == abs_file


def test_init_contract_relative_path_config_without_sentinel_not_modified(logging_handler, tmp_path):
	node = _make_node(_MinimalModule, Contract=_ContractWithPathConfig, contract_config={"file": "relative/path.txt"}, relative_path=tmp_path)
	assert node.contract.cfg.file == Path("relative/path.txt")


def test_init_module_receives_id(logging_handler):
	node = _make_node(_ModuleWithId)
	assert node.module.given_id == "test_node.module"


def test_init_contract_no_ports_warns(logging_handler):
	_make_node(_MinimalModule, Contract=_NoPortsContract)
	assert logging_handler.failure is False


def test_init_contract_with_ports(logging_handler):
	node = _make_node(_ModuleOneInput)
	assert "a" in node.contract.ports


def test_from_prenode_injects_branch_labels(logging_handler):
	# Labels supplied for an input port land on the contract's ContractPort.
	pre = _make_prenode(_ModuleOneInput)
	labels = frozenset({("origin", frozenset({"a"}))})
	node = Node.from_prenode(pre, {}, {"a": labels})
	assert node.contract.ports["a"].branch_labels == labels


# --- get_canonical_port (on PreNode) ---


def test_get_canonical_port_by_name(logging_handler):
	pre = _make_prenode(_ModuleTwoInputs)
	assert pre.get_canonical_port("a") == "a"
	assert pre.get_canonical_port("b") == "b"


def test_get_canonical_port_unknown_name(logging_handler):
	pre = _make_prenode(_ModuleTwoInputs)
	assert pre.get_canonical_port("nope") is None


def test_get_canonical_port_by_index(logging_handler):
	pre = _make_prenode(_ModuleTwoInputs)
	assert pre.get_canonical_port(1) == "a"
	assert pre.get_canonical_port(2) == "b"


def test_get_canonical_port_zero_returns_none(logging_handler):
	pre = _make_prenode(_ModuleTwoInputs)
	assert pre.get_canonical_port(0) is None


def test_get_canonical_port_out_of_range(logging_handler):
	pre = _make_prenode(_ModuleTwoInputs)
	assert pre.get_canonical_port(99) is None


# --- process_result — dispatch enqueues directly onto the destination Port ---


async def test_process_result_none_does_nothing(logging_handler):
	node = _make_node(_MinimalModule)
	await node.process_result(None)
	assert logging_handler.failure is False


async def test_process_result_non_tuple_dispatches_default(logging_handler):
	recv = Port(name="a")
	node = _make_node(_MinimalModule, dsts={"default": [recv]})
	await node.process_result(42)
	assert not recv.queue.empty()
	item = await recv.queue.get()
	assert item.payload == 42


async def test_process_result_named_tuple(logging_handler):
	recv = Port(name="a")
	node = _make_node(_MinimalModule, dsts={"out": [recv]})
	await node.process_result(("out", 7))
	item = await recv.queue.get()
	assert item.payload == 7


async def test_process_result_wrong_length_logs_error(logging_handler):
	node = _make_node(_MinimalModule)
	await node.process_result((1, 2, 3))
	assert logging_handler.failure is True


async def test_process_result_non_str_port_logs_error(logging_handler):
	node = _make_node(_MinimalModule)
	await node.process_result((42, "value"))
	assert logging_handler.failure is True


async def test_process_result_dst_count_increments(logging_handler):
	recv = Port(name="a")
	node = _make_node(_MinimalModule, dsts={"default": [recv]})

	await node.process_result(1)
	await node.process_result(2)

	assert node.dst_counts["default"][0] == 2  # two payloads sent to the one edge


async def test_process_result_payload_n_sequence(logging_handler):
	recv = Port(name="a")
	node = _make_node(_MinimalModule, dsts={"default": [recv]})

	await node.process_result("first")
	await node.process_result("second")

	items = []
	while not recv.queue.empty():
		items.append(recv.queue.get_nowait())

	assert items[0].n == 0
	assert items[1].n == 1


# --- process_result — output contract ---


async def test_process_result_output_contract_transforms_value(logging_handler):
	recv = Port(name="a")
	node = _make_node(_MinimalModule, output_contract=DoubleOutputContract, dsts={"default": [recv]})
	await node.process_result(21)
	item = await recv.queue.get()
	assert item.payload == 42


async def test_process_result_async_output_contract_transforms_value(logging_handler):
	recv = Port(name="a")
	node = _make_node(_MinimalModule, output_contract=AsyncSuffixOutputContract, dsts={"out": [recv]})
	await node.process_result(("out", "v"))
	item = await recv.queue.get()
	assert item.payload == "v:out"


async def test_process_result_general_contract_processes_outputs(logging_handler):
	# No output_contract, so the general contract serves the output end because it defines process_outputs.
	recv = Port(name="a")
	node = _make_node(_MinimalModule, Contract=GeneralOutputContract, dsts={"default": [recv]})
	await node.process_result(1)
	item = await recv.queue.get()
	assert item.payload == 2


async def test_process_result_output_contract_port_read_is_fatal(logging_handler):
	node = _make_node(_ModuleOneInput, output_contract=PortReadingOutputContract, dsts={})
	node.ports["a"].queue.put_nowait(Payload("src", 0, 1))
	with pytest.raises(typer.Exit):
		await node.process_result(1)
	assert node.ports["a"].queue.qsize() == 1  # the rejected read stole nothing from the next invocation


async def test_process_result_output_contract_typer_exit_propagates(logging_handler):
	node = _make_node(_MinimalModule, output_contract=ExitOutputContract, dsts={})
	with pytest.raises(typer.Exit):
		await node.process_result(1)


async def test_process_result_output_contract_exception_fatal(logging_handler):
	node = _make_node(_MinimalModule, output_contract=CrashOutputContract, dsts={})
	with pytest.raises(typer.Exit):
		await node.process_result(1)


async def test_process_result_no_destination_logs_info(logging_handler):
	recv = Port(name="a")
	# Wire from "other" but emit on "default" — no matching dst.
	node = _make_node(_MinimalModule, dsts={"other": [recv]})
	await node.process_result(42)  # emits on "default", not "other"
	assert logging_handler.failure is False  # INFO only


# --- run — module call forms ---


async def _run_node_with_input(Module, inputs_dict):
	"""Helper: run node once supplying given inputs, collect payloads dispatched to the destination Port."""
	collect = Port(name="x")

	class _CollectContract:
		def __init__(self, id, ports):  # pylint: disable=redefined-builtin
			self.id = id
			self.ports = ports
			self.called = False

		async def get_inputs(self):
			if self.called:
				return EndSentinel(self.id)
			self.called = True
			return {name: Payload("src", 0, val) for name, val in inputs_dict.items()}

	node = _make_node(Module, Contract=_CollectContract, dsts={"default": [collect]})
	await node.run()

	outputs = []
	while not collect.queue.empty():
		item = collect.queue.get_nowait()
		if isinstance(item, Payload):
			outputs.append(item.payload)
	return outputs


async def test_run_sync_return(logging_handler):
	outputs = await _run_node_with_input(_ModuleReturnDefault, {})
	assert outputs == [42]


async def test_run_async_return(logging_handler):
	outputs = await _run_node_with_input(_AsyncModule, {})
	assert outputs == [7]


async def test_run_sync_generator(logging_handler):
	outputs = await _run_node_with_input(_SyncGenModule, {})
	assert outputs == [1, 2, 3]


async def test_run_async_generator(logging_handler):
	outputs = await _run_node_with_input(_AsyncGenModule, {})
	assert outputs == [10, 20]


async def test_run_no_input_runs_once(logging_handler):
	outputs = await _run_node_with_input(_ModuleReturnDefault, {})
	assert len(outputs) == 1


async def test_run_module_exception_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		await _run_node_with_input(_CrashModule, {})


# --- Initialization — fatal paths ---


def test_module_unavailable_signature_fatal(logging_handler):
	with patch.object(inspect, "signature", side_effect=TypeError("uninspectable")):
		with pytest.raises(typer.Exit):
			_make_node(_MinimalModule)


def test_module_config_serde_error_fatal(logging_handler):
	with patch("rtl_comrade.node.from_dict", side_effect=SerdeError("bad config")):
		with pytest.raises(typer.Exit):
			_make_node(_ModuleWithConfigClass, config={"value": "wrong_type"})


def test_module_config_user_error_fatal(logging_handler):
	with patch("rtl_comrade.node.from_dict", side_effect=UserError("user error")):  # ty: ignore[invalid-argument-type] — ty misreads the class-level annotation `inner: Exception` as a constructor parameter; UserError has no custom __init__ and inherits Exception(*args)
		with pytest.raises(typer.Exit):
			_make_node(_ModuleWithConfigClass, config={"value": 0})


def test_module_init_exception_fatal(logging_handler):
	class _InitCrashModule:
		def __init__(self):
			raise RuntimeError("deliberate module init crash")

		def run(self):
			return None

	with pytest.raises(typer.Exit):
		_make_node(_InitCrashModule)


def test_module_init_typer_exit_propagates(logging_handler):
	with pytest.raises(typer.Exit):
		_make_node(_ModuleInitExitModule)


def test_module_invalid_tuple_structure_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		_make_node(_InvalidTupleModule)


def test_module_non_str_port_name_structure_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		_make_node(_NonStrPortNameModule)


def test_contract_unavailable_signature_fatal(logging_handler):
	# inspect.signature is called three times before Node init completes:
	#   1. Module.__init__ (module.py, inside GraphModule.from_module)
	#   2. Module.run    (structure.py, inside ModuleStructure)
	#   3. Contract.__init__ (node.py) ← want this to raise
	_orig = inspect.signature
	call_count = [0]

	def _patched(obj):
		call_count[0] += 1
		if call_count[0] == 3:
			raise TypeError("uninspectable contract")
		return _orig(obj)

	with patch.object(inspect, "signature", side_effect=_patched):
		with pytest.raises(typer.Exit):
			_make_node(_MinimalModule)


def test_contract_config_serde_error_fatal(logging_handler):
	# _MinimalModule has no 'config' param → from_dict not called for module.
	# _ContractConfigNoClass accepts config but has no Config class → only warn, no from_dict.
	# Use a contract WITH Config to trigger from_dict for contract.
	from serde import serde as _serde  # pylint: disable=import-outside-toplevel

	class _ContractWithSerdeCfg:
		@_serde
		class Config:
			x: int = 0

		def __init__(self, id, ports, config):  # pylint: disable=redefined-builtin
			self.id = id
			self.ports = ports

		async def get_inputs(self):
			return EndSentinel(self.id)

	with patch("rtl_comrade.contract.from_dict", side_effect=SerdeError("contract serde error")):
		with pytest.raises(typer.Exit):
			_make_node(_MinimalModule, Contract=_ContractWithSerdeCfg)


def test_contract_config_user_error_fatal(logging_handler):
	from serde import serde as _serde  # pylint: disable=import-outside-toplevel

	class _ContractWithSerdeCfg:
		@_serde
		class Config:
			x: int = 0

		def __init__(self, id, ports, config):  # pylint: disable=redefined-builtin
			self.id = id
			self.ports = ports

		async def get_inputs(self):
			return EndSentinel(self.id)

	with patch(
		"rtl_comrade.contract.from_dict",
		side_effect=UserError("contract user error"),  # ty: ignore[invalid-argument-type] — ty misreads the class-level annotation `inner: Exception` as a constructor parameter; UserError has no custom __init__ and inherits Exception(*args)
	):
		with pytest.raises(typer.Exit):
			_make_node(_MinimalModule, Contract=_ContractWithSerdeCfg)


def test_contract_no_config_class_warns(logging_handler):
	_make_node(_MinimalModule, Contract=_ContractConfigNoClass, contract_config={"x": 1})
	assert logging_handler.failure is False  # warn, not error


def test_contract_init_exception_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		_make_node(_MinimalModule, Contract=_ContractInitCrash)


def test_contract_init_typer_exit_propagates(logging_handler):
	with pytest.raises(typer.Exit):
		_make_node(_MinimalModule, Contract=_ContractInitExitContract)


# --- process_result — dsts not initialised ---


# --- run — fatal paths ---


async def test_run_invalid_enqueued_error_fatal(logging_handler):
	node = _make_node(_ModuleOneInput, dsts={})
	# Put a non-Payload/EndSentinel value directly into the port queue.
	node.ports["a"].queue.put_nowait(42)
	with pytest.raises(typer.Exit):
		await node.run()


async def test_run_get_inputs_exception_fatal(logging_handler):
	node = _make_node(_MinimalModule, Contract=_CrashGetInputsContract, dsts={})
	with pytest.raises(typer.Exit):
		await node.run()


async def test_run_get_inputs_typer_exit_propagates(logging_handler):
	node = _make_node(_MinimalModule, Contract=_ContractGetInputsExitContract, dsts={})
	with pytest.raises(typer.Exit):
		await node.run()


async def test_run_sync_contract_get_inputs(logging_handler):
	# Covers the sync `inputs = self.contract.get_inputs()` branch in Node.run().
	class _SyncTerminateContract:
		def __init__(self, id, ports):  # pylint: disable=redefined-builtin
			self.id = id
			self.ports = ports

		def get_inputs(self):  # intentionally sync
			return EndSentinel(self.id)

	node = _make_node(_MinimalModule, Contract=_SyncTerminateContract, dsts={})
	await node.run()  # should terminate cleanly via the sync EndSentinel


# --- run — finalise ---


async def test_run_sync_finalise_called(logging_handler):
	node = _make_node(_ModuleWithSyncFinalise, dsts={})
	await node.run()
	assert node.module.finalise_called is True


async def test_run_async_finalise_called(logging_handler):
	node = _make_node(_ModuleWithAsyncFinalise, dsts={})
	await node.run()
	assert node.module.finalise_called is True


async def test_run_no_finalise_runs_cleanly(logging_handler):
	node = _make_node(_MinimalModule, dsts={})
	await node.run()
	assert logging_handler.failure is False


async def test_run_finalise_exception_is_fatal(logging_handler):
	node = _make_node(_ModuleWithCrashingFinalise, dsts={})
	with pytest.raises(typer.Exit):
		await node.run()


async def test_run_finalise_typer_exit_propagates(logging_handler):
	node = _make_node(_ModuleWithFinaliseExitModule, dsts={})
	with pytest.raises(typer.Exit):
		await node.run()


async def test_run_non_callable_finalise_ignored(logging_handler):
	node = _make_node(_ModuleWithNonCallableFinalise, dsts={})
	await node.run()
	assert logging_handler.failure is False


async def test_run_finalise_plain_return_dispatched(logging_handler):
	outputs = await _run_node_with_input(_ModuleWithFinalisePlainReturn, {})
	assert outputs == [99]


async def test_run_finalise_named_port_return_dispatched(logging_handler):
	recv = Port(name="a")
	node = _make_node(_ModuleWithFinaliseNamedReturn, dsts={"out": [recv]})
	await node.run()
	item = await recv.queue.get()
	assert isinstance(item, Payload)
	assert item.payload == 42


async def test_run_finalise_sync_generator_dispatched(logging_handler):
	outputs = await _run_node_with_input(_ModuleWithFinaliseSyncGenerator, {})
	assert outputs == [1, 2, 3]


async def test_run_finalise_async_return_dispatched(logging_handler):
	outputs = await _run_node_with_input(_ModuleWithFinaliseAsyncReturn, {})
	assert outputs == [77]


async def test_run_finalise_async_generator_dispatched(logging_handler):
	outputs = await _run_node_with_input(_ModuleWithFinaliseAsyncGenerator, {})
	assert outputs == [10, 20]


# ---------------------------------------------------------------------------
# PreNode.from_config_node
# ---------------------------------------------------------------------------


class _SourceModule:
	def run(self):
		return 1


class _TwoInputsFromConfig:
	def run(self, a, b):
		return None


class _SimpleContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def get_inputs(self):
		return EndSentinel(self.id)


def _cfg_node(id_, module, contract="", mappings=None):
	return GraphConfigNode(id=id_, module=GraphConfigNodePlugin(name=module), contract=GraphConfigNodePlugin(name=contract), contract_port_mappings=mappings)


def _cfg_edge(src_node, src_port, dst_node, dst_port):
	return GraphConfigEdge(src=GraphConfigSrcPort(node=src_node, port=src_port), dst=GraphConfigDstPort(node=dst_node, port=dst_port))


class _KwargsModule:
	def run(self, **kwargs):
		return None


def _module_map():
	return { name: GraphModule.from_module(cls) for name, cls in [("source_mod", _SourceModule), ("two_input_mod", _TwoInputsFromConfig), ("kwargs_mod", _KwargsModule)] }


def _contract_map():
	return {"simple_contract": _SimpleContract}


def test_from_config_node_valid(logging_handler):
	node = _cfg_node("n1", "source_mod")
	pre = PreNode.from_config_node(node, [], _module_map(), {}, Path())
	assert pre.id == "n1"


def test_from_config_node_invalid_module(logging_handler):
	node = _cfg_node("n1", "nonexistent_mod")
	with pytest.raises(InvalidNodeModule) as exc_info:
		PreNode.from_config_node(node, [], _module_map(), {}, Path())
	assert exc_info.value.mod == "nonexistent_mod"


def test_from_config_node_with_contract(logging_handler):
	node = _cfg_node("n1", "source_mod", contract="simple_contract")
	pre = PreNode.from_config_node(node, [], _module_map(), _contract_map(), Path())
	assert pre.contract_definitions is not None


def test_from_config_node_missing_contract(logging_handler):
	from rtl_comrade.contract import MissingContractError  # pylint: disable=import-outside-toplevel
	node = _cfg_node("n1", "source_mod", contract="nonexistent")
	with pytest.raises(MissingContractError):
		PreNode.from_config_node(node, [], _module_map(), _contract_map(), Path())


def test_from_config_node_invalid_mapping_target(logging_handler):
	node = _cfg_node("n1", "two_input_mod", mappings={"cp": ["nonexistent"]})
	with pytest.raises(PortInvalidMappingTarget):
		PreNode.from_config_node(node, [], _module_map(), {}, Path())


def test_from_config_node_non_definite_positional(logging_handler):
	node = _cfg_node("agg", "kwargs_mod")
	edges = [ _cfg_edge("src", "default", "agg", 1) ]
	with pytest.raises(PortNonDefinitePositionalDestinationError):
		PreNode.from_config_node(node, edges, _module_map(), {}, Path())


def test_from_config_node_required_ports(logging_handler):
	node = _cfg_node("sink", "two_input_mod")
	edges = [ GraphConfigEdge(src=GraphConfigSrcPort(node="src"), dst=GraphConfigDstPort(node="sink", port="a", required=True)) ]
	pre = PreNode.from_config_node(node, edges, _module_map(), {}, Path())
	assert "a" in pre.required_ports


def test_from_config_node_definite_inputs_override_with_mappings(logging_handler):
	node = _cfg_node("n1", "kwargs_mod", mappings={"cp": ["x"]})
	pre = PreNode.from_config_node(node, [], _module_map(), {}, Path())
	assert pre.definite_inputs is True
