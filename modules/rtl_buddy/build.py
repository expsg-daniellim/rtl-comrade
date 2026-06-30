import os
import re
from pathlib import Path

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


FILELIST_OPTION_RE = re.compile(r"^((?:-v|-y|-[Ff])\s+|(\+(?:incdir|libext)\+))?(.*)$")


def filelist_extract(lines_in, unroll, fpath):
    prefix_parent = os.path.dirname(fpath)
    entries = []
    libexts = set()
    for line in lines_in:
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
            continue
        m = FILELIST_OPTION_RE.fullmatch(line)
        if not m or not m.group(3):
            log.error("filelist_malformed_line", line=line)
            continue
        if m.group(2):
            line_option, line_path = m.group(2), m.group(3)
        elif m.group(1):
            line_option, line_path = m.group(1).strip() + " ", m.group(3)
        else:
            line_option, line_path = None, m.group(3)
        line_path = os.path.expandvars(line_path)
        if line_option == '-f ':
            log.fatal("filelist_lower_f_not_allowed", line=line)
        elif line_option == '-F ' and unroll:
            path_next = os.path.join(prefix_parent, line_path)
            try:
                with open(path_next) as f:
                    entries.extend(filelist_extract(f.readlines(), unroll, path_next))
            except OSError as e:
                raise KeyError(f"F-include error {path_next}: {e}") from e
        elif line_option == '+libext+':
            libexts.update(line_path.split('+'))
        else:
            entries.append((os.path.join(prefix_parent, line_path), line_option))
    if len(libexts) != 0:
        entries.append(("+".join(libexts), "+libext+"))
    return entries


def filelist_process(entries, work_dir, deduplicate):
    out_lines = []
    for abs_path, line_option in entries:
        if line_option == '+libext+':
            line = f'+libext+{abs_path}\n'
        else:
            rel = os.path.relpath(abs_path, work_dir)
            if line_option in ('+incdir+', '-y '):
                if not os.path.isdir(abs_path):
                    log.error("filelist_incdir_not_a_dir", path=abs_path)
            else:
                if not os.path.isfile(abs_path):
                    log.error("filelist_file_not_found", path=abs_path)
            line = f'{line_option}{rel}\n' if line_option else f'{rel}\n'
        if deduplicate and line in out_lines:
            continue
        out_lines.append(line)
    return out_lines


class WriteFilelistMod:
    def run(self, test:TestConfig, model:KeyedValue[ModelConfig], work_dir:Path):
        test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())
        path = Path(work_dir) / f"run.{test_tag}.f"
        try:
            model_cfg = model.value
            model_path = model_cfg.get_model_path()
            model_dir = os.path.dirname(os.path.abspath(model_path)) if model_path else str(work_dir)
            entries = filelist_extract(model_cfg.get_filelist(), True, os.path.join(model_dir, "models.yaml"))
            entries.extend(filelist_extract(test.get_testbench().get_filelist(), True, str(Path(work_dir) / "tests.yaml")))
            lines = filelist_process(entries, str(work_dir), True)
            with open(path, "w") as f:
                f.write("// rtl-buddy generated model filelist\n")
                f.writelines(lines)
            yield ("test", test)
            yield ("filelist", KeyedValue(test.key, path))
        except FileNotFoundError:
            log.error("filelist_dir_not_found", key=test.key, test_name=test.get_name(), path=str(path))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"output directory missing for {path}"))
        except IsADirectoryError:
            log.error("filelist_is_directory", key=test.key, test_name=test.get_name(), path=str(path))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"{path} is a directory"))
        except PermissionError as e:
            log.error("filelist_permission_denied", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot write {path}"))
        except (KeyError, AttributeError) as e:
            log.error("filelist_resolve_error", key=test.key, test_name=test.get_name(), path=str(path), err=str(e))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"filelist resolve failed: {e}"))
        except OSError as e:
            log.error("filelist_write_error", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror, errno=e.errno)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot write {path}"))
