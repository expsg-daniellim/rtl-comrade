from click.exceptions import NoArgsIsHelpError
import click
from serde import serde, field, SerdeError
from serde.yaml import from_yaml
from yaml.error import MarkedYAMLError
from yaml.reader import ReaderError
import structlog
import typer

from argparse import ArgumentParser
import asyncio
import logging
import os
from pathlib import Path
from typing import cast, Annotated, Literal, Any

from .graph import Graph
from .logging import initialise_logging, HarnessLogger

DEFAULT_RTL_COMRADE_CONFIG_NAME = "rtl_comrade_config.yaml"
LOGGING_LEVELS = { "NOTSET": logging.NOTSET, "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL, "FATAL": logging.CRITICAL }

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@serde
class CommandConfig:
	path: str
	help: str = field(default="")

@serde
class RtlComradeConfig:
	commands: dict[str, CommandConfig]

# Ascend until repo root or filesystem root or config is found
def search_for_config(name:str, path:Path) -> RtlComradeConfig|None:
	if path.is_dir():
		is_git_top = False
		for child in path.iterdir():
			if child.is_dir() and child.name == ".git":
				is_git_top = True
			if child.is_file() and child.name == name:
				return from_yaml(RtlComradeConfig, child.read_text())

		if is_git_top or path.parent == path:
			return None
		else:
			return search_for_config(name, path.parent)
	elif path.name == name:
		return from_yaml(RtlComradeConfig, path.read_text())
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
		self.handler = initialise_logging(LOGGING_LEVELS[args.level])

		# Look for config
		config = search_for_config(args.config_file, Path(os.getcwd()))
		if config is None:
			log.fatal('invalid_config', config_name=args.config_file)

		# Initialise CLI app
		self.app = typer.Typer(no_args_is_help=True, invoke_without_command=True, callback=self.main)

		# TODO: normalise config paths (relative to config, not runner)

		for (name, command) in config.commands.items():
			# TODO: lazy load graphs
			try:
				graph = Graph.from_file(command.path)
			except UnicodeDecodeError as e:
				log.fatal('invalid_unicode', reason=e.reason, invalid_slice=e.object[e.start:e.end].decode(encoding=e.encoding or 'utf-8', errors='replace'), exc_info=e)
			except FileNotFoundError as e:
				log.fatal('not_found', exc_info=e)
			except IsADirectoryError as e:
				log.fatal('is_directory', exc_info=e)
			except PermissionError as e:
				log.fatal('permission_denied', exc_info=e)
			except OSError as e:
				log.fatal('os_error', err=e.strerror, errno=e.errno, exc_info=e)
			except SerdeError as e:
				log.fatal('serde_error', message=str(e), exc_info=e)
			except MarkedYAMLError as e:
				mark_fields:dict[str, Any] = {}
				if e.problem_mark is not None:
					mark_fields['problem_name'] = e.problem_mark.name
					mark_fields['index'] = e.problem_mark.index
					mark_fields['line'] = e.problem_mark.line
					mark_fields['column'] = e.problem_mark.line
					mark_fields['pointer'] = e.problem_mark.pointer
				log.fatal('yaml.marked', problem=e.problem, **mark_fields, exc_info=e)
			except ReaderError as e:
				log.fatal('yaml.reader', error_name=e.name, position=e.position, character=e.character, encoding=e.encoding, reason=e.reason, exc_info=e)
			self.app.command(name, help=command.help, no_args_is_help=(len(graph.sig.parameters) > 0))(graph.construct_run(self.cleanup))

	# Dummy callback to reflect variables read by argparse into typer
	def main(self, ctx:typer.Context, config_file:Annotated[str, typer.Option(help="File name of config file defining command/graphs.")]=DEFAULT_RTL_COMRADE_CONFIG_NAME, level:Annotated[Literal[*list(LOGGING_LEVELS.keys())], typer.Option(case_sensitive=False, help="Logging level.")]="info"):
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
			log.error('usage_error', message=e.message, param=e.param_hint, param_type=e.param_type)
			exit_code = e.exit_code
		except click.BadParameter as e:
			log.error('usage_error', message=e.message, param=e.param_hint)
			exit_code = e.exit_code
		except click.BadOptionUsage as e:
			log.error('usage_error', message=e.message, option=e.option_name)
			exit_code = e.exit_code
		except click.UsageError as e:
			log.error('usage_error', message=e.message)
			exit_code = e.exit_code
		return exit_code or 0

	def cleanup(self):
		"""Raise ``typer.Exit(1)`` if the graph logged any failure during execution.

		Returns:
			None.
		"""

		if self.handler.failure:
			raise typer.Exit(1)

		# Exit naturally
