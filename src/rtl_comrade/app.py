from click.exceptions import NoArgsIsHelpError
import click
from serde import serde, field
from serde.yaml import from_yaml
import structlog
import typer

from argparse import ArgumentParser
import asyncio
import logging
import os
from pathlib import Path
from typing import cast, Annotated, Literal

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
		# TODO: parse graph config for CLI options (dynamically generate command? Probs)

		for (name, command) in config.commands.items():
			self.app.command(name, help=command.help)(lambda: self.run_graph(command.path))

	# Dummy callback to reflect variables read by argparse
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
			exit_code = e.code
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

	def run_graph(self, config_path:str):
		graph = Graph.from_file(config_path)
		asyncio.run(graph.run())

		if self.handler.failure:
			raise typer.Exit(1)

		# Exit naturally
