class AddMod:
	def run(self, a:int, b:int):
		return int(a) + int(b)

class ALUMod:
	def run(self, a:int, b:int, op:int):
		if op == 0:
			return int(a) + int(b)
		elif op == 1:
			return int(a) - int(b)
		else:
			raise f"invalid op {op}"
