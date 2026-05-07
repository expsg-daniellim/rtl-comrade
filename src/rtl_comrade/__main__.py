import asyncio
import logging
import sys

from .graph import Graph
from .logging import initialise_logging

# TODO: pydoc strings (for the benefit of ChatGPT)
# TODO: pydantic
# TODO: test multi-outputs
# TODO: debug logging

def main() -> int:
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
