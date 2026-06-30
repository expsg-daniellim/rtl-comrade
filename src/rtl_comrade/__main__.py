"""Current CLI entrypoint for running a graph from the command line."""

import typer
from .app import App

# TODO: debug logging

def main() -> int:
	"""Run the configured graph and return a process exit code.

	Returns:
		``0`` if no errors were encountered during the run, otherwise ``1``.
	"""

	exit_code = 0
	try:
		app = App()
		exit_code = app.run()
	except typer.Exit as e:
		exit_code = e.exit_code

	return exit_code

if __name__ == '__main__':
	raise SystemExit(main())
