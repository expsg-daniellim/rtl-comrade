"""Contract resolution: configured contract names to constructed contract objects.

A node may declare up to three contracts. ``contract`` is the general one, covering both input scheduling and output
processing; ``input_contract`` and ``output_contract`` each override it on their own end. This module resolves those
names against the loaded contract plugins, checks each class satisfies the interface its role requires, and constructs
them once the node's ports are known.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
import inspect
from inspect import Parameter
from pathlib import Path
from typing import cast, Any, Generic, Literal, Self, TypeVar

from serde import from_dict, SerdeError
from serde.compat import UserError
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
import typer

from .api import ContractPort
from .config import GraphConfigNode
from .contract_default import DefaultContract
from .logging import HarnessLogger
from .port import Port

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass(slots=True)
class MissingContractError(Exception):
	"""Raised when a node names a contract that is not among the loaded contract plugins.

	Attributes:
		field: The node config field naming the contract — ``"contract"``, ``"input_contract"``, or ``"output_contract"``.
		name: The unresolved contract name.
		available: Exported names of the contract plugins that were loaded.
	"""

	field: str
	name: str
	available: list[str]

@dataclass(slots=True)
class MissingContractFunctionError(Exception):
	"""Raised when a resolved contract class lacks the callable its role requires.

	An input contract must expose ``get_inputs``, an output contract ``process_outputs``.

	Attributes:
		field: The node config field naming the contract.
		name: The contract name as configured.
		method: The missing method name.
		available_functions: The function members the contract class does define.
	"""

	field: str
	name: str
	method: str
	available_functions: list[str]

@dataclass(slots=True)
class MissingContractParameterError(Exception):
	"""Raised when a contract function omits a parameter the harness must pass to it.

	Attributes:
		field: The node config field naming the contract.
		name: The contract name as configured.
		function: The function whose signature was checked.
		parameter: The missing parameter name.
	"""

	field: str
	name: str
	function: str
	parameter: str

@dataclass(slots=True)
class InvalidContractParameterTypeError(Exception):
	"""Raised when a contract function parameter is annotated with a type the harness cannot supply.

	Attributes:
		field: The node config field naming the contract.
		name: The contract name as configured.
		function: The function whose signature was checked.
		parameter: The offending parameter name.
		type_: The rejected annotation, rendered as a string.
	"""

	field: str
	name: str
	function: str
	parameter: str
	type_: str

T = TypeVar('T')
ContractType = Literal['input_contract', 'contract', 'output_contract']
@dataclass(slots=True, frozen=True)
class ContractDefinition(Generic[T]):
	"""One resolved contract class, the config it will be constructed with, and the role it fills.

	Produced by ``from_config`` during graph construction, when only names are known, and turned into a live contract
	object by ``construct`` once the node's ports exist.

	Attributes:
		type_: The role this contract fills, which decides both the interface ``from_config`` demands of it and how the Node invokes it.
		Contract: The resolved contract plugin class.
		config: Contract-specific configuration, passed to the constructor when it accepts ``config``.
	"""

	type_: ContractType
	Contract: type[T]
	config: dict = field(default_factory=dict)

	def construct(self, node_id:str, ports:dict[str, ContractPort], relative_path:Path=Path()) -> T:
		"""Instantiate the contract, injecting only the constructor arguments it declares.

		``config``, ``id`` and ``ports`` are each passed only when named in ``__init__``. When the contract defines a
		nested ``Config`` type, ``config`` is deserialised through serde first and its ``{graph}``-prefixed Path fields
		are resolved against ``relative_path``. An output contract that omits ``ports`` is unremarkable; an input one
		that omits them is warned about, having nothing to read.

		Args:
			node_id: Runtime node id; the injected ``id`` is this suffixed with ``.contract``.
			ports: The node's ContractPort surface.
			relative_path: Base path used to resolve ``{graph}``-relative config paths.

		Returns:
			The constructed contract object.
		"""

		bind_contextvars(context='harness.node.contract', node=node_id, contract=self.Contract.__name__, field=self.type_)

		try:
			contract_init_sig = inspect.signature(self.Contract.__init__)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', exc_info=e)

		contract_init_args:dict[str, Any] = {}

		if 'config' in contract_init_sig.parameters:
			contract_config = self.config
			if hasattr(self.Contract, 'Config'):
				try:
					contract_config = from_dict(self.Contract.Config, contract_config)

					# Relativise config paths (if not absolute)
					for (attr, val) in [ (attr, getattr(contract_config, attr)) for attr in dir(contract_config) if not callable(getattr(contract_config, attr)) and not (attr.startswith('__') and attr.endswith('__')) ]:
						if isinstance(val, Path) and not val.is_absolute() and val.parts[0] == '{graph}':
							setattr(contract_config, attr, relative_path / Path(*val.parts[1:]))
				except SerdeError as e:
					log.fatal('config.deserialise.serde_error', exc_info=e)
				except UserError as e:
					log.fatal('config.deserialise.user_error', exc_info=e)
			else:
				log.warn('config.mismatch')

			contract_init_args['config'] = contract_config

		if 'id' in contract_init_sig.parameters:
			contract_init_args['id'] = node_id + '.contract'

		if 'ports' in contract_init_sig.parameters:
			contract_init_args['ports'] = ports
		elif self.type_ == 'input_contract' or self.type_ == 'contract': # pylint: disable=consider-using-in
			# Warn for this one because it's a pretty pointless input contract that has no input ports
			log.warn('init.no_ports')

		try:
			contract = self.Contract(**contract_init_args)
		except typer.Exit:
			raise
		except Exception as e:
			log.fatal('init', exc_info=e)

		unbind_contextvars('context', 'node', 'contract', 'field')
		return contract

	@classmethod
	def from_config(cls, contract_type:ContractType, contract_name:str, contract_mappings:dict[str, type[Any]], config:dict) -> Self|None:
		"""Resolve a configured contract name to its plugin class and check the class satisfies its role.

		An input contract must expose ``get_inputs``, an output contract ``process_outputs``. ``process_outputs`` is
		additionally signature-checked — for a general ``contract`` only when it defines one at all, since output
		processing is optional in that role.

		Args:
			contract_type: The role the named contract will fill.
			contract_name: The configured contract plugin name; ``""`` means unset.
			contract_mappings: Loaded contract plugin classes keyed by exported name.
			config: Contract-specific configuration from the node config.

		Returns:
			The ContractDefinition, or ``None`` when an unset ``input_contract``/``output_contract`` leaves that end to ``contract``. An unset ``contract`` resolves to the built-in DefaultContract rather than ``None``.

		Raises:
			MissingContractError: The name is not among the loaded contract plugins.
			MissingContractFunctionError: The class lacks the callable its role requires.
			MissingContractParameterError: ``process_outputs`` omits ``port`` or ``value``.
			InvalidContractParameterTypeError: ``process_outputs`` annotates ``port`` as something other than ``str``.
		"""

		Contract = None
		if contract_name == '':
			if contract_type == 'contract':
				Contract = DefaultContract
			else:
				return None
		elif contract_name not in contract_mappings:
			raise MissingContractError(contract_type, contract_name, list(contract_mappings.keys()))
		else:
			Contract = contract_mappings[contract_name]

		if contract_type == 'input_contract' or contract_type == 'contract': # pylint: disable=consider-using-in
			if not (hasattr(Contract, 'get_inputs') and callable(getattr(Contract, 'get_inputs'))):
				raise MissingContractFunctionError(contract_type, contract_name, 'get_inputs', [ fn for fn, _ in inspect.getmembers(Contract, predicate=lambda obj: inspect.isfunction(obj) and not inspect.isbuiltin(obj))])

		if contract_type == 'output_contract': # pylint: disable=consider-using-in
			if not (hasattr(Contract, 'process_outputs') and callable(getattr(Contract, 'process_outputs'))):
				raise MissingContractFunctionError(contract_type, contract_name, 'process_outputs', [ fn for fn, _ in inspect.getmembers(Contract, predicate=lambda obj: inspect.isfunction(obj) and not inspect.isbuiltin(obj))])

		if contract_type == 'output_contract' or (contract_type == 'contract' and hasattr(Contract, 'process_outputs') and callable(getattr(Contract, 'process_outputs'))):
			# Validate signature
			sig = inspect.signature(getattr(Contract, 'process_outputs'))
			if not 'port' in sig.parameters:
				raise MissingContractParameterError(contract_type, contract_name, 'process_outputs', 'port')
			if not (sig.parameters['port'].annotation is str or sig.parameters['port'].annotation is Parameter.empty):
				raise InvalidContractParameterTypeError(contract_type, contract_name, 'process_outputs', 'port', str(sig.parameters['port'].annotation))

			if not 'value' in sig.parameters:
				raise MissingContractParameterError(contract_type, contract_name, 'process_outputs', 'value')

		return cls(contract_type, Contract, config)

C = TypeVar('C')
IC = TypeVar('IC')
OC = TypeVar('OC')
@dataclass(slots=True, frozen=True)
class ContractDefinitions(Generic[C, IC, OC]):
	"""A GraphConfigNode's contracts fully unravelled, with overrides taken into account.

	``contract`` is always present, falling back to the built-in DefaultContract when the node names none. A non-``None``
	``input_contract`` or ``output_contract`` overrides it on that end.

	Attributes:
		contract: The general contract, serving whichever end is not overridden.
		input_contract: Overrides ``contract`` for ``get_inputs``, or ``None`` to leave the input end to ``contract``.
		output_contract: Overrides ``contract`` for ``process_outputs``, or ``None`` to leave the output end to ``contract``.
	"""

	contract: ContractDefinition[C]
	input_contract: ContractDefinition[IC]|None
	output_contract: ContractDefinition[OC]|None

	def construct(self, node_id:str, ports:OrderedDict[str, Port], input_labels:dict[str, frozenset], required_ports:set[str]|None=None, relative_path:Path=Path()) -> tuple[C, IC|None, OC|None]:
		"""Build the node's ContractPort surface and construct every contract defined against it.

		All of the node's contracts share one set of ContractPort adapters, so an input and an output contract on the
		same node see the same per-port ``state``.

		Args:
			node_id: Runtime node id from graph configuration.
			ports: The node's runtime input ports, keyed by canonical name.
			input_labels: Control-dependence labels per input-port name, from graph propagation.
			required_ports: Canonical names of input ports marked required in the graph config.
			relative_path: Base path used to resolve ``{graph}``-relative config paths.

		Returns:
			The constructed ``(contract, input_contract, output_contract)``, the latter two ``None`` where that end is not overridden.
		"""

		if required_ports is None:
			required_ports = set()

		contract_ports = { name: ContractPort(name=name, get=port.get, try_get=port.try_get, has_ended=port.has_ended, has_default=port.has_default, required=name in required_ports, branch_labels=input_labels.get(name, frozenset())) for (name, port) in ports.items() }

		contract = self.contract.construct(node_id, contract_ports, relative_path)
		input_contract = self.input_contract.construct(node_id, contract_ports, relative_path) if self.input_contract is not None else None
		output_contract = self.output_contract.construct(node_id, contract_ports, relative_path) if self.output_contract is not None else None
		return contract, input_contract, output_contract

	@classmethod
	def from_node_config(cls, node:GraphConfigNode, contract_mappings:dict[str, Any]) -> Self:
		"""Resolve all three of a config node's contract fields.

		Args:
			node: The graph config node whose contract fields are being resolved.
			contract_mappings: Loaded contract plugin classes keyed by exported name.

		Returns:
			The resolved ContractDefinitions.

		Raises:
			MissingContractError: A named contract is not among the loaded contract plugins.
			MissingContractFunctionError: A resolved contract lacks the callable its role requires.
			MissingContractParameterError: ``process_outputs`` omits ``port`` or ``value``.
			InvalidContractParameterTypeError: ``process_outputs`` annotates ``port`` as something other than ``str``.
		"""

		input_contract =ContractDefinition.from_config('input_contract', node.input_contract, contract_mappings, node.input_contract_config)
		output_contract = ContractDefinition.from_config('output_contract', node.output_contract, contract_mappings, node.output_contract_config)
		contract = ContractDefinition.from_config('contract', node.contract, contract_mappings, node.contract_config)

		if contract is None: # To satisfy the type checker
			log.fatal('unreachable_error')

		return cls(contract, input_contract, output_contract)

	@classmethod
	def default(cls) -> Self:
		"""Build the contract set for nodes the harness creates itself, such as the virtual CLI nodes.

		Returns:
			ContractDefinitions holding the built-in DefaultContract and no overrides.
		"""

		return cls(ContractDefinition('contract', DefaultContract, {}), None, None)
