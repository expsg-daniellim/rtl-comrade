"""Unit tests for node.py — Node construction, get_canonical_port, accept, process_result, run."""

import pytest
from collections import OrderedDict

from rtl_comrade.api import Payload, EndSentinel
from rtl_comrade.contract_default import DefaultContract
from rtl_comrade.node import Node, Connection
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
    from serde import serde as _serde

    @_serde
    class Config:
        value: int = 0

    def __init__(self, config):
        self.cfg = config

    def run(self):
        return None


class _ModuleWithId:
    def __init__(self, id):
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


class _NoPortsContract:
    def __init__(self, id):
        self.id = id

    async def get_inputs(self):
        return EndSentinel(self.id)


def _make_node(Module, config=None, Contract=None, contract_config=None):
    if config is None:
        config = {}
    if Contract is None:
        Contract = DefaultContract
    if contract_config is None:
        contract_config = {}
    return Node(id="test_node", Module=Module, config=config, Contract=Contract, contract_config=contract_config)


# --- Initialization ---

def test_init_no_params(logging_handler):
    node = _make_node(_MinimalModule)
    assert node.id == "test_node"
    assert isinstance(node.module, _MinimalModule)


def test_init_config_no_config_class_warns(logging_handler):
    node = _make_node(_ModuleWithConfig, config={"x": 1})
    assert logging_handler.failure is False  # warn, not error


def test_init_config_with_config_class(logging_handler):
    node = _make_node(_ModuleWithConfigClass, config={"value": 7})
    assert node.module.cfg.value == 7


def test_init_module_receives_id(logging_handler):
    node = _make_node(_ModuleWithId)
    assert node.module.given_id == "test_node.module"


def test_init_contract_no_ports_warns(logging_handler):
    node = _make_node(_MinimalModule, Contract=_NoPortsContract)
    assert logging_handler.failure is False


def test_init_contract_with_ports(logging_handler):
    node = _make_node(_ModuleOneInput)
    assert "a" in node.contract.ports


# --- get_canonical_port ---

def test_get_canonical_port_by_name(logging_handler):
    node = _make_node(_ModuleTwoInputs)
    assert node.get_canonical_port("a") == "a"
    assert node.get_canonical_port("b") == "b"


def test_get_canonical_port_unknown_name(logging_handler):
    node = _make_node(_ModuleTwoInputs)
    assert node.get_canonical_port("nope") is None


def test_get_canonical_port_by_index(logging_handler):
    node = _make_node(_ModuleTwoInputs)
    assert node.get_canonical_port(1) == "a"
    assert node.get_canonical_port(2) == "b"


def test_get_canonical_port_zero_returns_none(logging_handler):
    node = _make_node(_ModuleTwoInputs)
    assert node.get_canonical_port(0) is None


def test_get_canonical_port_out_of_range(logging_handler):
    node = _make_node(_ModuleTwoInputs)
    assert node.get_canonical_port(99) is None


# --- accept ---

async def test_accept_queues_payload(logging_handler):
    node = _make_node(_ModuleOneInput)
    node.set_dsts([])
    payload = Payload("up", 0, 1)
    await node.accept(payload, "a")
    assert not node.ports["a"].queue.empty()


async def test_accept_unknown_port_logs_error(logging_handler):
    node = _make_node(_ModuleOneInput)
    node.set_dsts([])
    before = node.ports["a"].queue.qsize()
    await node.accept(Payload("up", 0, 1), "nonexistent")
    assert logging_handler.failure is True
    assert node.ports["a"].queue.qsize() == before  # queue unchanged


# --- process_result ---

async def test_process_result_none_does_nothing(logging_handler):
    node = _make_node(_MinimalModule)
    node.set_dsts([])
    await node.process_result(None)
    assert logging_handler.failure is False


async def test_process_result_non_tuple_dispatches_default(logging_handler):
    recv_node = _make_node(_ModuleOneInput)
    recv_node.set_dsts([])
    node = _make_node(_MinimalModule)
    conn = Connection(self_port="default", other_node=recv_node, other_port="a")
    node.set_dsts([conn])
    await node.process_result(42)
    assert not recv_node.ports["a"].queue.empty()
    item = await recv_node.ports["a"].queue.get()
    assert item.payload == 42


async def test_process_result_named_tuple(logging_handler):
    recv_node = _make_node(_ModuleOneInput)
    recv_node.set_dsts([])
    node = _make_node(_MinimalModule)
    conn = Connection(self_port="out", other_node=recv_node, other_port="a")
    node.set_dsts([conn])
    await node.process_result(("out", 7))
    item = await recv_node.ports["a"].queue.get()
    assert item.payload == 7


async def test_process_result_wrong_length_logs_error(logging_handler):
    node = _make_node(_MinimalModule)
    node.set_dsts([])
    await node.process_result((1, 2, 3))
    assert logging_handler.failure is True


async def test_process_result_non_str_port_logs_error(logging_handler):
    node = _make_node(_MinimalModule)
    node.set_dsts([])
    await node.process_result((42, "value"))
    assert logging_handler.failure is True


async def test_process_result_dst_count_increments(logging_handler):
    recv_node = _make_node(_ModuleOneInput)
    recv_node.set_dsts([])
    node = _make_node(_MinimalModule)
    conn = Connection(self_port="default", other_node=recv_node, other_port="a")
    node.set_dsts([conn])

    await node.process_result(1)
    await node.process_result(2)

    key = (recv_node.id, "a")
    assert node.dst_counts[key] == 1  # started at -1, now 1


async def test_process_result_payload_n_sequence(logging_handler):
    recv_node = _make_node(_ModuleOneInput)
    recv_node.set_dsts([])
    node = _make_node(_MinimalModule)
    conn = Connection(self_port="default", other_node=recv_node, other_port="a")
    node.set_dsts([conn])

    await node.process_result("first")
    await node.process_result("second")

    items = []
    while not recv_node.ports["a"].queue.empty():
        items.append(await recv_node.ports["a"].queue.get())

    assert items[0].n == 0
    assert items[1].n == 1


async def test_process_result_no_destination_logs_info(logging_handler):
    recv_node = _make_node(_ModuleOneInput)
    recv_node.set_dsts([])
    node = _make_node(_MinimalModule)
    # Wire to "other" port but emit on "default" — no matching dst
    conn = Connection(self_port="other", other_node=recv_node, other_port="a")
    node.set_dsts([conn])
    await node.process_result(42)  # emits on "default", not "other"
    assert logging_handler.failure is False  # INFO only


# --- run — module call forms ---

async def _run_node_with_input(Module, inputs_dict):
    """Helper: run node once supplying given inputs, collect outputs."""
    outputs = []

    class _CollectContract:
        def __init__(self, id, ports):
            self.id = id
            self.ports = ports
            self._called = False

        async def get_inputs(self):
            if self._called:
                return EndSentinel(self.id)
            self._called = True
            return {name: Payload("src", 0, val) for name, val in inputs_dict.items()}

    class _CollectNode:
        id = "collect"
        ports = {"x": Port(name="x")}

        async def accept(self, val, port):
            if isinstance(val, Payload):
                outputs.append(val.payload)

        def set_dsts(self, dsts):
            self.dsts = dsts

    collect = _CollectNode()
    node = Node(id="runner", Module=Module, config={}, Contract=_CollectContract)
    conn = Connection(self_port="default", other_node=collect, other_port="x")
    node.set_dsts([conn])
    collect.set_dsts([])
    await node.run()
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
    with pytest.raises(SystemExit):
        await _run_node_with_input(_CrashModule, {})
