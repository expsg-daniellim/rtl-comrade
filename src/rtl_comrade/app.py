from argparse import ArgumentParser
import itertools
import logging
import os
from pathlib import Path
from typing import cast, Annotated, Literal, Any

from click.exceptions import NoArgsIsHelpError
import click
from serde import serde, field, SerdeError
from serde.yaml import from_yaml
from yaml.error import MarkedYAMLError
from yaml.reader import ReaderError
from structlog.stdlib import ProcessorFormatter
import structlog
import typer

from .config_graph import GraphConfig
from .graph import Graph
from .loader_logger import LoggingPlugin
from .logging import initialise_logging, HarnessLogger

DEFAULT_RTL_COMRADE_CONFIG_NAME = "rtl_comrade_config.yaml"
LOGGING_LEVELS = { "NOTSET": logging.NOTSET, "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL, "FATAL": logging.CRITICAL }
LogLevel = Literal[*list(LOGGING_LEVELS.keys())] # ty: ignore[invalid-type-form] — Literal built dynamically from LOGGING_LEVELS keys, which ty cannot accept as literal members

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@serde
class CommandConfig:
	path: Path
	help: str = field(default="")

@serde
class RtlComradeConfig:
	commands: dict[str, CommandConfig]
	relative_path: Path = field(default=Path(), skip=True)

# Ascend until repo root or filesystem root or config is found
def search_for_config(name:str, path:Path) -> RtlComradeConfig|None:
	if path.is_dir():
		is_git_top = False
		for child in path.iterdir():
			if child.is_dir() and child.name == ".git":
				is_git_top = True
			if child.is_file() and child.name == name:
				config = from_yaml(RtlComradeConfig, child.read_text())
				config.relative_path = path
				return config

		if is_git_top or path.parent == path:
			return None
		else:
			return search_for_config(name, path.parent)
	elif path.name == name:
		config = from_yaml(RtlComradeConfig, path.read_text())
		config.relative_path = path
		return config
	else:
		return None

class App:
	def __init__(self):
		# Parse preliminary options
		parser = ArgumentParser(add_help=False)
		parser.add_argument("--config-file", default=DEFAULT_RTL_COMRADE_CONFIG_NAME)
		parser.add_argument("--level", type=str.upper, choices=list(LOGGING_LEVELS.keys()), default="info")
		args, _ = parser.parse_known_args()

		# Initialise logging handler
		self.handler, self.root_logger = initialise_logging(LOGGING_LEVELS[args.level])
		self.processors:list = []

		# Look for config
		config = search_for_config(args.config_file, Path(os.getcwd()))
		if config is None:
			log.fatal('invalid_config', context='harness.app.config', config_name=args.config_file)

		# Initialise CLI app
		self.app = typer.Typer(no_args_is_help=True, invoke_without_command=True, callback=self.main)

		for (name, command) in config.commands.items():
			try:
				graph_config = GraphConfig.from_file(config.relative_path / command.path)
			except UnicodeDecodeError as e:
				log.fatal('invalid_unicode', context='harness.app.load', reason=e.reason, invalid_slice=e.object[e.start:e.end].decode(encoding=e.encoding or 'utf-8', errors='replace'), exc_info=e)
			except FileNotFoundError as e:
				log.fatal('not_found', context='harness.app.load', exc_info=e)
			except IsADirectoryError as e:
				log.fatal('is_directory', context='harness.app.load', exc_info=e)
			except PermissionError as e:
				log.fatal('permission_denied', context='harness.app.load', exc_info=e)
			except OSError as e:
				log.fatal('os_error', context='harness.app.load', err=e.strerror, errno=e.errno, exc_info=e)
			except SerdeError as e:
				log.fatal('serde_error', context='harness.app.load', message=str(e), exc_info=e)
			except MarkedYAMLError as e:
				mark_fields:dict[str, Any] = {}
				if e.problem_mark is not None:
					mark_fields['problem_name'] = e.problem_mark.name
					mark_fields['index'] = e.problem_mark.index
					mark_fields['line'] = e.problem_mark.line
					mark_fields['column'] = e.problem_mark.line
					mark_fields['pointer'] = e.problem_mark.pointer
				log.fatal('yaml.marked', context='harness.app.load', problem=e.problem, **mark_fields, exc_info=e)
			except ReaderError as e:
				log.fatal('yaml.reader', context='harness.app.load', error_name=e.name, position=e.position, character=e.character, encoding=e.encoding, reason=e.reason, exc_info=e)

			# Register command
			self.app.command(name, help=command.help, no_args_is_help=len(graph_config.sig.parameters) > 0)(Graph.construct_run(graph_config, self.setup_logging, self.cleanup))

	# Dummy callback to reflect variables read by argparse into typer
	def main(self, ctx:typer.Context, config_file:Annotated[str, typer.Option(help="File name of config file defining command/graphs.")]=DEFAULT_RTL_COMRADE_CONFIG_NAME, level:Annotated[LogLevel, typer.Option(case_sensitive=False, help="Logging level.")]="info"):
		# Also prints help when there is an argument but no command, which typer fails to catch
		if ctx.invoked_subcommand is None:
			click.echo(ctx.get_help())
			raise typer.Exit(0)

	def run(self):
		try:
			exit_code = self.app(standalone_mode=False)
		except NoArgsIsHelpError:
			exit_code = 0
		except typer.Exit as e:
			exit_code = e.exit_code
		except typer.Abort:
			exit_code = 1
		except click.MissingParameter as e:
			log.error('usage_error', context='harness.app.cli', message=e.message, param=e.param_hint, param_type=e.param_type)
			exit_code = e.exit_code
		except click.BadParameter as e:
			log.error('usage_error', context='harness.app.cli', message=e.message, param=e.param_hint)
			exit_code = e.exit_code
		except click.BadOptionUsage as e:
			log.error('usage_error', context='harness.app.cli', message=e.message, option=e.option_name)
			exit_code = e.exit_code
		except click.UsageError as e:
			log.error('usage_error', context='harness.app.cli', message=e.message)
			exit_code = e.exit_code

		return exit_code or 0

	def setup_logging(self, processors:list[LoggingPlugin], handlers:list[LoggingPlugin], include_default:bool):
		"""Construct and install the resolved processor chain and custom root handlers for a graph run.

		Args:
			processors: Ordered processor specs to construct into the chain.
			handlers: Root-handler specs to construct and append to the root logger.
			include_default: Whether to keep the harness's terminal ConsoleRenderer in the chain.

		Returns:
			None.
		"""

		# Keep the constructed chain so cleanup can finalise processors if need be
		self.processors = [ spec.construct() for spec in processors ]
		if include_default:
			self.processors.append(structlog.dev.ConsoleRenderer())

		self.handler.render = bool(self.processors)
		# Skip rebuilding the formatter when there is no terminal renderer; a processors=[] ProcessorFormatter has nothing to render.
		if self.processors:
			# Derive the foreign chain from the live structlog config (its trailing entry is wrap_for_formatter) so it can't drift from a cached copy.
			self.handler.setFormatter(ProcessorFormatter(processors=self.processors, foreign_pre_chain=structlog.get_config()["processors"][:-1]))

		for spec in handlers:
			self.root_logger.addHandler(spec.construct())

	def cleanup(self):
		"""Raise ``typer.Exit(1)`` if the graph logged any failure during execution.

		Returns:
			None.
		"""

		# Finalise before the failure check so handlers/processors flush even on a failing run.
		for logger in itertools.chain(self.processors, self.root_logger.handlers):
			if callable(finalise := getattr(logger, "finalise", None)):
				finalise()

		if self.handler.failure:
			raise typer.Exit(1)

		# Exit naturally
