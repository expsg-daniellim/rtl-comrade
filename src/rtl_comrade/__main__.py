import asyncio
import sys

from .graph import Graph

# TODO: pydoc strings (for the benefit of ChatGPT)
# TODO: pydantic
# TODO: test multi-outputs
# TODO: debug logging

def main() -> int:
	graph_file = sys.argv[1] if len(sys.argv) >= 2 else 'graph.yaml'

	graph = Graph.from_file(graph_file)
	asyncio.run(graph.run())

	return 0

if __name__ == '__main__':
	raise SystemExit(main())
