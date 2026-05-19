import structlog

log = structlog.get_logger()


class AddMod:
	def run(self, a: int, b: int):
		return int(a) + int(b)


class ALUMod:
	id: str

	def run(self, a: int, b: int, op: int):
		if int(op) == 0:
			return int(a) + int(b)
		elif int(op) == 1:
			return int(a) - int(b)
		else:
			log.error("invalid_op", op=op)
