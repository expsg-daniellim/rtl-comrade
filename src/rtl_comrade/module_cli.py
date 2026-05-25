from serde import serde
import structlog

log = structlog.get_logger()

class ModuleCLI:
	"""Virtual harness module that bridges a single CLI argument into the graph.

	One instance is created per distinct CLI edge during graph construction.
	The harness sets ``value`` before execution begins; ``run`` emits it once.
	"""

	@serde
	class Config:
		"""Configuration for ``ModuleCLI``.

		Attributes:
			cli: The CLI parameter name this node corresponds to.
		"""

		cli: str

	def __init__(self, id:str, config:Config):
		"""Initialise the node with its id and CLI parameter name.

		Args:
			id: The runtime node id assigned by the harness.
			config: Serde-deserialised config carrying the CLI parameter name.

		Returns:
			None.
		"""

		self.id = id
		self.cli = config.cli
		self.value = None

	def run(self):
		"""Emit the injected CLI value downstream.

		Returns:
			The value set by the harness before execution, or ``None`` if it was never injected.
		"""

		if self.value is None:
			log.error("empty_cli_arg", id=self.id)
		return self.value
