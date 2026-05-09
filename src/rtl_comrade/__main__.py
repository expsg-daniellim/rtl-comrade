"""Current CLI entrypoint for running a graph from the command line."""

import asyncio
import logging
import sys

from .graph import Graph
from .logging import initialise_logging

# TODO: pydantic
# TODO: test multi-outputs
# TODO: debug logging

def main() -> int:
	"""Run the configured graph and return a process exit code.

	Returns:
		``0`` if no error-level logs were emitted during the run, otherwise ``1``.
	"""

	# TODO: read log level from env/cli arg
	handler = initialise_logging(logging.INFO)

	graph_file = sys.argv[1] if len(sys.argv) >= 2 else 'graph.yaml'

	graph = Graph.from_file(graph_file)
	asyncio.run(graph.run())

	if handler.failure:
		return 1
	else:
		return 0

if __name__ == '__main__':
	raise SystemExit(main())
