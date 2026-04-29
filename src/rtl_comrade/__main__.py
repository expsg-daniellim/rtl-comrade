import asyncio

from .graph import Graph

# TODO: pydoc strings (for the benefit of ChatGPT)
# TODO: pydantic
# TODO: test multi-outputs

def main() -> int:
	graph = Graph.from_file('graph.yaml')
	asyncio.run(graph.run())

	return 0

if __name__ == '__main__':
	raise SystemExit(main())
