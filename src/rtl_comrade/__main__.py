"""Current CLI entrypoint for running a graph from the command line."""

from .app import App

# TODO: debug logging

def main() -> int:
	"""Run the configured graph and return a process exit code.

	Returns:
		``0`` if no errors were encountered during the run, otherwise ``1``.
	"""

	app = App()
	return app.run()

if __name__ == '__main__':
	raise SystemExit(main())
