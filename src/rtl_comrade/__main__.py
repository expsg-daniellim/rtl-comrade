import asyncio
from serde import serde
import importlib.util
import importlib
import inspect

from .graph import Graph
from .module import load_module_folder

# TODO: pydoc strings (for the benefit of ChatGPT)
# TODO: pydantic
# TODO: test multi-outputs

def main() -> int:
	graph = Graph.from_file('graph.yaml')
	asyncio.run(graph.run())

	return 0

if __name__ == '__main__':
	raise SystemExit(main())
