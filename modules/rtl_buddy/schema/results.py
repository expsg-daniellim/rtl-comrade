from dataclasses import dataclass
from enum import Enum


class ResultType(Enum):
	PARSE = "parse"
	COMPILE_FAIL = "compile_fail"
	SIM_TIMEOUT = "sim_timeout"
	PREP = "prep"
	EARLY_STOP = "early_stop"
	SKIP = "skip"


@dataclass(frozen=True)
class TestResult:
	__test__ = False  # domain type, not a pytest test class despite the Test* name

	key:str
	test_name:str
	type_:ResultType
	result:str
	desc:str

	def is_pass(self) -> bool:
		return self.result in ("PASS", "SKIP")

	@classmethod
	def compile_fail(cls, key:str, test_name:str) -> "TestResult":
		return cls(key=key, test_name=test_name, type_=ResultType.COMPILE_FAIL, result="FAIL", desc="Compile failed")

	@classmethod
	def sim_timeout(cls, key:str, test_name:str) -> "TestResult":
		return cls(key=key, test_name=test_name, type_=ResultType.SIM_TIMEOUT, result="FAIL", desc="Sim hit timeout")

	@classmethod
	def early_stop(cls, key:str, test_name:str, desc:str) -> "TestResult":
		return cls(key=key, test_name=test_name, type_=ResultType.EARLY_STOP, result="NA", desc=desc)

	@classmethod
	def skip(cls, key:str, test_name:str, desc:str) -> "TestResult":
		return cls(key=key, test_name=test_name, type_=ResultType.SKIP, result="SKIP", desc=desc)

	@classmethod
	def prep(cls, key:str, test_name:str, desc:str) -> "TestResult":
		return cls(key=key, test_name=test_name, type_=ResultType.PREP, result="FAIL", desc=desc)

	@classmethod
	def parse(cls, key:str, test_name:str, result:str, desc:str) -> "TestResult":
		return cls(key=key, test_name=test_name, type_=ResultType.PARSE, result=result, desc=desc)
