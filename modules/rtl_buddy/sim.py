import dataclasses

from modules.rtl_buddy.schema import KeyedValue
from modules.rtl_buddy.schema.suite import TestConfig


class ExpandRunsMod:
    def run(self, test:TestConfig, simv:KeyedValue[str], run_ids:list = [None]):
        for run_id in run_ids:
            nk = test.key if run_id is None else f"{test.key}#{run_id}"
            yield ("test", dataclasses.replace(test, key=nk))
            yield ("run_id", KeyedValue(nk, run_id))
            yield ("simv", KeyedValue(nk, simv.value))
