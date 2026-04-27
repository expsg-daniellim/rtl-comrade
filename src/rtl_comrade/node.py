from asyncio import Queue
from collections import OrderedDict
from dataclasses import dataclass
import inspect
from inspect import signature
from serde import serde, from_dict

@dataclass
class Connection:
	self_port: int
	other_node: NodeWrapper
	other_port: int

class NodeWrapper:
	def __init__(self, Node, id:str, config:dict):
		self.id = id
		# TODO: warn about config acceptance
		init_sig = signature(Node.__init__)

		if 'config' in init_sig.parameters:
			if hasattr(Node, 'Config'):
				config = from_dict(Node.Config, config)
			self.node = Node(config=config)
		else:
			self.node = Node()

		if not hasattr(self.node, 'run'):
			raise "node is not runnable"

		run_sig = signature(self.node.run)
		# self.ports = list(map(lambda port:run_sig.parameters.keys())
		self.ports = OrderedDict({ param: Queue() for param in run_sig.parameters.keys() })

	def set_dsts(self, dsts:list[Connection]):
		self.dsts = dsts

	# TODO: named ports
	async def accept(self, val, port:str|int=1):
		port_name = None
		if type(port) is str and port in self.ports.keys():
			port_name = port
		elif type(port) is int and port - 1 < len(self.ports) and port - 1 >= 0:
			port_name = list(self.ports.keys())[port - 1]
		else:
			raise "invalid port type"

		await self.ports[port_name].put(val)

	# TODO: type this function
	async def process_result(self, res):
		port = res[0] if type(res) is tuple else 1
		value = res[1] if type(res) is tuple else res

		for dst in filter(lambda dst: dst.self_port == port, self.dsts):
			await dst.other_node.accept(val=value, port=dst.other_port)

	async def run(self):
		inputs = [0] # Dummy value to bootstrap loop
		while len(inputs) > 0:
			# TODO: option for persistent inputs (persistent until refresh)
			inputs = [ await queue.get() for queue in self.ports.values() ]
			if any(map(lambda i: i == None, inputs)):
				break

			res = None
			if inspect.iscoroutinefunction(self.node.run):
				# TODO: dictionary spread
				res = await self.node.run(*inputs)
			else:
				res = self.node.run(*inputs)

			if res is not None:
				if inspect.isgenerator(res):
					for r in res:
						await self.process_result(r)
				else:
					await self.process_result(res)
		
		for dst in self.dsts:
			await dst.other_node.accept(val=None, port=dst.other_port)
