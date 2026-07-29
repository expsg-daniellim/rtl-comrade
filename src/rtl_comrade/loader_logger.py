"""Logging-plugin loading: resolving a graph's logging config into processor/handler specs."""

from __future__ import annotations
from collections.abc import MutableMapping
from dataclasses import dataclass
import inspect
import logging
from pathlib import Path
from typing import cast, get_args, get_origin, Any

from serde import serde, field, from_dict, SerdeError
from serde.compat import UserError
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
import typer

from .logging import HarnessLogger
from .loader_utils import import_plugin_file

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@serde
@dataclass(slots=True, frozen=True)
class LoggingHandlerConfig:
	"""One custom logging handler plugin reference from a graph YAML file.

	Attributes:
		path: Plugin file whose directory stays on sys.path for sibling imports; resolved relative to the graph file.
		name: The exported callable/class to select from that file.
		config: Passed as ``__init__(config=...)`` only if the selected class declares a ``config`` param.
	"""

	path: Path
	name: str
	config: dict = field(default_factory=dict)

	def load(self, relative_path:Path=Path()) -> Any:
		"""Import this handler's file and return the selected object, classified but not constructed.

		Returns:
			The selected object: a ``logging.Handler`` subclass, a processor class, or a processor function/instance.
		"""

		# import_plugin_file binds plugin/file context (and context='harness.load.plugin') for its own import-phase diagnostics.
		if self.path.is_absolute():
			resolved = self.path
			module = import_plugin_file(resolved, None, 'logging')
		else:
			resolved = relative_path / self.path
			module = import_plugin_file(resolved, self.path.with_suffix('').as_posix().replace('/', '.'), 'logging')
		# Rebind context for the selection below; name tags every diagnostic.
		bind_contextvars(context='harness.load.logging', name=self.name)
		try:
			plugin = getattr(module, self.name)

			if isinstance(plugin, type) and issubclass(plugin, logging.Handler):
				pass  # a Handler subclass; the consumer constructs it
			elif callable(plugin):
				# A function or already-built instance cannot consume config; non-empty config is a mistake.
				if not inspect.isclass(plugin) and self.config:
					log.warn('config.mismatch')
			else:
				log.fatal('invalid_logging_handler')
		finally:
			unbind_contextvars('context', 'plugin', 'file', 'name')

		return plugin

@serde
@dataclass(slots=True, frozen=True)
class LoggingConfig:
	"""Per-graph custom logging configuration.

	Attributes:
		handlers: Custom handler plugin references, loaded lazily at graph invocation.
		include_default: Whether the harness handler's ConsoleRenderer stays terminal.
	"""

	handlers: list[LoggingHandlerConfig] = field(default_factory=list)
	include_default: bool = field(default=True)

	def load(self, relative_path:Path=Path()) -> tuple[list[LoggingPlugin], list[LoggingPlugin]]:
		"""Resolve this logging config into processor and root-handler specs for the consumer to construct.

		Args:
			relative_path: Base path used to resolve ``{graph}``-relative handler config paths during construction.

		Returns:
			A ``(processors, handlers)`` pair: ordered processor specs and root-handler specs. Specs are imported,
			classified, and signature-checked, but not yet constructed. The terminal-renderer decision is read from
			``include_default`` by the caller.
		"""

		# structlog's EventDict shape: a bare dict/MutableMapping or a MutableMapping parameterised with exactly (str, Any).
		def is_event_dict(annotation:Any) -> bool:
			if annotation is dict or annotation is MutableMapping:
				return True
			origin = get_origin(annotation)
			return isinstance(origin, type) and issubclass(origin, MutableMapping) and get_args(annotation) == (str, Any)

		# Classify each entry into processor specs vs root-handler specs, preserving processor order.
		processors:list[LoggingPlugin] = []
		handlers:list[LoggingPlugin] = []
		for handler_config in self.handlers:
			plugin = handler_config.load(relative_path)
			spec = LoggingPlugin(plugin=plugin, config=handler_config.config, relative_path=relative_path, name=handler_config.name)
			if isinstance(plugin, type) and issubclass(plugin, logging.Handler):
				handlers.append(spec)
			else:
				processors.append(spec)

		# Hard-reject (no warn-and-continue) processors whose signature does not match structlog's Processor shape.
		# Under include_default: false the last processor is terminal and must return str; all others return an EventDict.
		bind_contextvars(context='harness.load.logging')
		try:
			for (i, spec) in enumerate(processors):
				bind_contextvars(name=spec.name)
				terminal = not self.include_default and i == len(processors) - 1
				plugin = spec.plugin

				# Validate on __call__: a class is not yet constructed so drop its self; an instance's bound __call__ already has; a function is itself.
				if inspect.isclass(plugin):
					bound, skip = plugin.__call__, 1
				elif inspect.isfunction(plugin) or inspect.ismethod(plugin):
					bound, skip = plugin, 0
				else:
					bound, skip = plugin.__call__, 0

				try:
					# eval_str resolves string annotations (plugins use `from __future__ import annotations`) against the callable's __globals__.
					sig = inspect.signature(bound, eval_str=True)
				except (NameError, TypeError) as e:
					log.fatal('signature.unresolved_annotation', exc_info=e)

				params = [ p for p in sig.parameters.values() if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD) ][skip:]
				if len(params) != 3:
					log.fatal('signature.arity', expected=3, found=len(params))

				# param 1 (logger): unconstrained on purpose — structlog types it Any/WrappedLogger.
				if params[0].annotation is not inspect.Parameter.empty and params[0].annotation is not Any:
					log.fatal('signature.param', parameter=params[0].name, position=1, expected='Any or unannotated')

				# param 2 (method)
				if params[1].annotation is not str:
					log.fatal('signature.param', parameter=params[1].name, position=2, expected='str')

				# param 3 (event_dict)
				if not is_event_dict(params[2].annotation):
					log.fatal('signature.param', parameter=params[2].name, position=3, expected='EventDict')

				ret = sig.return_annotation
				if terminal and ret is not str:
					log.fatal('signature.return', expected='str')
				elif not terminal and not is_event_dict(ret):
					log.fatal('signature.return', expected='EventDict')

			# include_default: false with no processors (harness renders nothing) and no handlers means nothing renders.
			if not self.include_default and len(processors) == 0 and len(handlers) == 0:
				log.warn('no_renderers')
		finally:
			unbind_contextvars('context', 'name')

		return (processors, handlers)

@dataclass(slots=True, frozen=True)
class LoggingPlugin:
	"""A logging plugin resolved from config but not yet constructed.

	Attributes:
		plugin: The class, function, or instance selected from the plugin file.
		config: Raw config dict, deserialised into ``plugin.Config`` when ``plugin`` is a class.
		relative_path: Base path for resolving ``{graph}``-relative config paths during construction.
		name: The configured handler name, for diagnostics.
	"""

	plugin: Any
	config: dict
	relative_path: Path
	name: str

	def construct(self) -> Any:  # pylint: disable=inconsistent-return-statements
		"""Construct this resolved logging plugin for installation.

		Instantiates a class (deserialising its ``Config`` and relativising ``{graph}`` paths), or passes a
		function/already-built instance through unchanged.

		Returns:
			A ``logging.Handler`` instance or a processor callable.
		"""

		plugin = self.plugin
		if not inspect.isclass(plugin):
			return plugin # a function or already-built instance is used as-is

		config = None
		bind_contextvars(context='harness.load.logging', name=self.name)

		# Initialise plugin with available init params
		try:
			init_sig = inspect.signature(plugin.__init__)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', exc_info=e)

		if 'config' in init_sig.parameters:
			if hasattr(plugin, 'Config'):
				try:
					config = from_dict(plugin.Config, self.config)

					# Relativise config paths (if not absolute)
					for (attr, val) in [ (attr, getattr(config, attr)) for attr in dir(config) if not callable(getattr(config, attr)) and not (attr.startswith('__') and attr.endswith('__')) ]:
						if isinstance(val, Path) and not val.is_absolute() and val.parts[0] == '{graph}':
							setattr(config, attr, self.relative_path / Path(*val.parts[1:]))
				except SerdeError as e:
					log.fatal('config.deserialise.serde_error', exc_info=e)
				except UserError as e:
					log.fatal('config.deserialise.user_error', exc_info=e)
			else:
				log.warn('config.mismatch')
				config = self.config

		try:
			if config is not None:
				return plugin(config=config)
			else:
				return plugin()
		except typer.Exit:
			raise
		except Exception as e:
			log.fatal('init', exc_info=e)
		finally:
			unbind_contextvars('context', 'name')
