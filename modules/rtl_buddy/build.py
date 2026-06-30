import structlog

from modules.rtl_buddy.schema import RootConfig, TestResult, KeyedValue, ModelConfig
from modules.rtl_buddy.schema.suite import TestConfig

log = structlog.get_logger()


class RunPreprocMod:
    def run(self, test:TestConfig, model:KeyedValue[ModelConfig], root_cfg:RootConfig):
        preproc = test.get_preproc_path()
        if preproc is None:
            yield ("test", test)
            yield ("model", model)
            return
        name = test.model
        ns = {"logger": log, "test_cfg": test, "root_cfg": root_cfg}
        try:
            with open(preproc) as f:
                code = f.read()
        except FileNotFoundError:
            log.error("preproc_script_not_found", key=test.key, test_name=test.get_name(), preproc_path=str(preproc))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"preproc script not found: {preproc}")); return
        except PermissionError as e:
            log.error("preproc_script_permission", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), err=e.strerror)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read preproc script {preproc}")); return
        except OSError as e:
            log.error("preproc_script_read_error", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), err=e.strerror, errno=e.errno)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read preproc script {preproc}")); return
        test.model = model.value  # expose resolved ModelConfig to the script; restored on both exits below
        try:
            exec(compile(code, preproc, "exec"), ns)
        except Exception as e:
            test.model = name
            log.error("preproc_script_error", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), exc_info=e)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"preproc script raised: {e}")); return
        test.model = name  # restore before forwarding so the test edge always carries the name string
        yield ("test", test)
        yield ("model", model)
