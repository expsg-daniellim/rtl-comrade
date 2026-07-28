"""Unit tests for contract.py — per-role interface checks, ContractPort construction, and node-config resolution."""

from collections import OrderedDict
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.api import EndSentinel
from rtl_comrade.config import GraphConfigNodePlugin
from rtl_comrade.contract import ContractDefinition, ContractDefinitions, InvalidContractParameterTypeError, MissingContractFunctionError, MissingContractParameterError
from rtl_comrade.contract_default import DefaultContract
from rtl_comrade.port import Port


class InputOnlyContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def get_inputs(self):
		return EndSentinel(self.id)


class OutputContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	def process_outputs(self, port:str, value):
		return (port, value)


class UnannotatedPortContract:
	def process_outputs(self, port, value):
		return value


class NoPortParamContract:
	def process_outputs(self, value):
		return value


class NonStrPortParamContract:
	def process_outputs(self, port:int, value):
		return value


class NoValueParamContract:
	def process_outputs(self, port:str):
		return port


class GeneralBadOutputContract:
	"""Serves both ends, but its process_outputs omits the port argument the harness must pass."""

	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def get_inputs(self):
		return EndSentinel(self.id)

	def process_outputs(self, value):
		return value


MAPPINGS = {
	"input_only": InputOnlyContract,
	"output": OutputContract,
	"unannotated_port": UnannotatedPortContract,
	"no_port": NoPortParamContract,
	"non_str_port": NonStrPortParamContract,
	"no_value": NoValueParamContract,
	"general_bad_output": GeneralBadOutputContract,
}


# --- from_config — output-contract role checks ---


def test_output_contract_without_process_outputs_raises():
	with pytest.raises(MissingContractFunctionError) as exc_info:
		ContractDefinition.from_config('output_contract', 'input_only', MAPPINGS, {})
	assert exc_info.value.method == 'process_outputs'
	assert 'get_inputs' in exc_info.value.available_functions


def test_output_contract_valid_signature_resolves():
	definition = ContractDefinition.from_config('output_contract', 'output', MAPPINGS, {})
	assert definition.Contract is OutputContract
	assert definition.type_ == 'output_contract'


def test_output_contract_unannotated_port_accepted():
	# An unannotated port is as good as one annotated str — the harness only rejects a wrong annotation.
	definition = ContractDefinition.from_config('output_contract', 'unannotated_port', MAPPINGS, {})
	assert definition.Contract is UnannotatedPortContract


def test_output_contract_missing_port_parameter_raises():
	with pytest.raises(MissingContractParameterError) as exc_info:
		ContractDefinition.from_config('output_contract', 'no_port', MAPPINGS, {})
	assert exc_info.value.function == 'process_outputs'
	assert exc_info.value.parameter == 'port'


def test_output_contract_non_str_port_annotation_raises():
	with pytest.raises(InvalidContractParameterTypeError) as exc_info:
		ContractDefinition.from_config('output_contract', 'non_str_port', MAPPINGS, {})
	assert exc_info.value.parameter == 'port'
	assert 'int' in exc_info.value.type_


def test_output_contract_missing_value_parameter_raises():
	with pytest.raises(MissingContractParameterError) as exc_info:
		ContractDefinition.from_config('output_contract', 'no_value', MAPPINGS, {})
	assert exc_info.value.parameter == 'value'


def test_general_contract_process_outputs_is_signature_checked():
	# A general contract's process_outputs is optional, but is checked once it exists.
	with pytest.raises(MissingContractParameterError) as exc_info:
		ContractDefinition.from_config('contract', 'general_bad_output', MAPPINGS, {})
	assert exc_info.value.parameter == 'port'


def test_general_contract_without_process_outputs_skips_check():
	definition = ContractDefinition.from_config('contract', 'input_only', MAPPINGS, {})
	assert definition.Contract is InputOnlyContract


# --- ContractDefinitions.construct ---


def test_construct_defaults_required_ports_to_empty(logging_handler):
	contract, input_contract, output_contract = ContractDefinitions.default().construct("n1", OrderedDict({"a": Port(name="a")}), {})
	assert isinstance(contract, DefaultContract)
	assert contract.ports["a"].required is False
	assert input_contract is None
	assert output_contract is None


def test_construct_marks_required_ports(logging_handler):
	contract, _, _ = ContractDefinitions.default().construct("n1", OrderedDict({"a": Port(name="a"), "b": Port(name="b")}), {}, {"b"})
	assert contract.ports["a"].required is False
	assert contract.ports["b"].required is True


def test_construct_shares_one_port_surface_across_roles(logging_handler):
	definitions = ContractDefinitions(ContractDefinition('contract', InputOnlyContract, {}), None, ContractDefinition('output_contract', OutputContract, {}))
	contract, _, output_contract = definitions.construct("n1", OrderedDict({"a": Port(name="a")}), {})
	assert contract.ports["a"] is output_contract.ports["a"]


# --- from_config ---


def test_from_config_unset_fields_resolve_to_default_contract():
	definitions = ContractDefinitions.from_config(GraphConfigNodePlugin(), GraphConfigNodePlugin(), GraphConfigNodePlugin(), MAPPINGS)
	assert definitions.contract.Contract is DefaultContract
	assert definitions.input_contract is None
	assert definitions.output_contract is None


def test_from_config_unresolved_contract_fatal(logging_handler):
	# The general contract never resolves to None in practice; the guard exists to satisfy the type checker.
	with patch.object(ContractDefinition, 'from_config', return_value=None):
		with pytest.raises(typer.Exit):
			ContractDefinitions.from_config(GraphConfigNodePlugin(), GraphConfigNodePlugin(), GraphConfigNodePlugin(), MAPPINGS)
