"""Unit tests for loader_logger.py — logging-plugin selection, signature validation,
and construction (LoggingPlugin.construct)."""

import inspect
import logging
from pathlib import Path
import textwrap
from unittest.mock import patch

import pytest
import structlog
import typer
from serde.compat import UserError

from rtl_comrade.loader_logger import LoggingPlugin, LoggingHandlerConfig, LoggingConfig


def _write(tmp_path, name, src):
	f = tmp_path / name
	f.write_text(textwrap.dedent(src))
	return f


def _handler_config(path, name, config=None):
	return LoggingHandlerConfig(path=path, name=name, config=config or {})


# Resolve a handler config to its object (handler_config.load), then construct it the way App.setup_logging does.
def _construct(path, name, config=None, relative_path=Path()):
	hc = _handler_config(path, name, config)
	return LoggingPlugin(plugin=hc.load(), config=hc.config, relative_path=relative_path, name=name).construct()


def test_construct_passes_callable_through():
	# A function/instance spec is used as-is, not re-constructed.
	def proc(logger, method_name, event_dict):
		return event_dict
	assert LoggingPlugin(plugin=proc, config={}, relative_path=Path(), name="x").construct() is proc


class _Plugin:
	def __init__(self):
		pass


def test_construct_unavailable_signature_type_error_fatal(logging_handler):
	# A class plugin whose __init__ signature raises TypeError on inspection is fatal.
	with patch.object(inspect, "signature", side_effect=TypeError("uninspectable")):
		with pytest.raises(typer.Exit):
			LoggingPlugin(plugin=_Plugin, config={}, relative_path=Path(), name="x").construct()


def test_construct_unavailable_signature_value_error_fatal(logging_handler):
	# A class plugin whose __init__ signature raises ValueError on inspection is fatal.
	with patch.object(inspect, "signature", side_effect=ValueError("no signature")):
		with pytest.raises(typer.Exit):
			LoggingPlugin(plugin=_Plugin, config={}, relative_path=Path(), name="x").construct()


# ---------------------------------------------------------------------------
# LoggingHandlerConfig.load + LoggingPlugin.construct — selection, classification, construction
# ---------------------------------------------------------------------------


def test_load_processor_function(logging_handler, tmp_path):
	# A plain processor function is returned as-is (not instantiated).
	f = _write(tmp_path, "p.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		def add_marker(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
			event_dict['marker'] = True
			return event_dict
	""")
	obj = _handler_config(f, "add_marker").load()
	assert callable(obj)
	assert obj.__name__ == "add_marker"


def test_load_relative_path(logging_handler, tmp_path):
	_write(tmp_path, "p.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		def add_marker(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
			event_dict['marker'] = True
			return event_dict
	""")
	obj = _handler_config(Path("p.py"), "add_marker").load(relative_path=tmp_path)
	assert callable(obj)
	assert obj.__name__ == "add_marker"


def test_load_processor_class_no_config(logging_handler, tmp_path):
	# A processor class with no `config` __init__ param is instantiated via obj().
	f = _write(tmp_path, "p.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		class Marker:
			def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
				return event_dict
	""")
	obj = _construct(f, "Marker")
	assert callable(obj)
	assert type(obj).__name__ == "Marker"


def test_load_processor_class_with_config(logging_handler, tmp_path):
	# A processor class with a Config dataclass deserialises the config dict.
	f = _write(tmp_path, "p.py", """\
		from dataclasses import dataclass
		from serde import serde

		class Tagger:
			@serde
			@dataclass
			class Config:
				tag: str

			def __init__(self, config):
				self.tag = config.tag

			def __call__(self, logger, method_name, event_dict):
				event_dict['tag'] = self.tag
				return event_dict
	""")
	obj = _construct(f, "Tagger", {"tag": "hi"})
	assert obj.tag == "hi"


def test_load_processor_class_config_param_without_config_class_warns(logging_handler, tmp_path):
	# A class whose __init__ declares `config` but has no Config dataclass:
	# the raw config dict is passed and a warning emitted.
	f = _write(tmp_path, "p.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		class Tagger:
			def __init__(self, config):
				self.config = config

			def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
				return event_dict
	""")
	obj = _construct(f, "Tagger", {"k": "v"})
	assert obj.config == {"k": "v"}
	assert logging_handler.failure is False


def test_load_handler_type_no_config(logging_handler, tmp_path):
	# A logging.Handler subclass with no config param is instantiated.
	f = _write(tmp_path, "h.py", """\
		import logging

		class CollectingHandler(logging.Handler):
			records = []
			def emit(self, record):
				CollectingHandler.records.append(record)
	""")
	obj = _construct(f, "CollectingHandler")
	assert isinstance(obj, logging.Handler)


def test_load_handler_type_with_config(logging_handler, tmp_path):
	# A logging.Handler subclass with a Config dataclass is built with deserialised config.
	f = _write(tmp_path, "h.py", """\
		import logging
		from dataclasses import dataclass
		from serde import serde

		class ConfHandler(logging.Handler):
			@serde
			@dataclass
			class Config:
				level_name: str

			def __init__(self, config):
				super().__init__()
				self.level_name = config.level_name

			def emit(self, record):
				pass
	""")
	obj = _construct(f, "ConfHandler", {"level_name": "INFO"})
	assert isinstance(obj, logging.Handler)
	assert obj.level_name == "INFO"


def test_load_handler_config_path_relativised(logging_handler, tmp_path):
	# A {graph}-relative Path field in the Config is resolved against relative_path.
	f = _write(tmp_path, "h.py", """\
		import logging
		from pathlib import Path
		from dataclasses import dataclass
		from serde import serde

		class FileHandler(logging.Handler):
			@serde
			@dataclass
			class Config:
				out: Path

			def __init__(self, config):
				super().__init__()
				self.out = config.out

			def emit(self, record):
				pass
	""")
	obj = _construct(f, "FileHandler", {"out": "{graph}/log.txt"}, tmp_path)
	assert obj.out == tmp_path / "log.txt"


def test_load_non_callable_is_fatal(logging_handler, tmp_path):
	# A selected object that is neither a Handler nor callable is fatal.
	f = _write(tmp_path, "p.py", "VALUE = 42\n")
	with pytest.raises(typer.Exit):
		_handler_config(f, "VALUE").load()


def test_load_function_with_config_warns(logging_handler, tmp_path):
	# Supplying config for a plain function is a mistake → warn, but still returns the function.
	f = _write(tmp_path, "p.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		def proc(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
			return event_dict
	""")
	obj = _handler_config(f, "proc", {"k": "v"}).load()
	assert callable(obj)
	assert logging_handler.failure is False


def test_load_class_config_deserialise_error_fatal(logging_handler, tmp_path):
	# A config dict that does not match the Config dataclass is fatal.
	f = _write(tmp_path, "p.py", """\
		from dataclasses import dataclass
		from serde import serde

		class Tagger:
			@serde
			@dataclass
			class Config:
				tag: int

			def __init__(self, config):
				self.tag = config.tag

			def __call__(self, logger, method_name, event_dict):
				return event_dict
	""")
	with pytest.raises(typer.Exit):
		_construct(f, "Tagger", {"tag": "not_an_int"})


def test_load_class_init_raises_fatal(logging_handler, tmp_path):
	# A class whose __init__ raises during instantiation is fatal.
	f = _write(tmp_path, "p.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		class Bad:
			def __init__(self):
				raise RuntimeError('boom')

			def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
				return event_dict
	""")
	with pytest.raises(typer.Exit):
		_construct(f, "Bad")


def test_load_class_config_user_error_fatal(logging_handler, tmp_path):
	# A serde UserError raised while processing the Config type is fatal.
	f = _write(tmp_path, "p.py", """\
		from dataclasses import dataclass
		from serde import serde

		class Tagger:
			@serde
			@dataclass
			class Config:
				tag: str

			def __init__(self, config):
				self.tag = config.tag

			def __call__(self, logger, method_name, event_dict):
				return event_dict
	""")
	with patch("rtl_comrade.loader_logger.from_dict", side_effect=UserError(ValueError("bad type"))):
		with pytest.raises(typer.Exit):
			_construct(f, "Tagger", {"tag": "x"})


def test_load_config_class_init_fatal_propagates(logging_handler, tmp_path):
	# A config-bearing class whose __init__ calls log.fatal (typer.Exit) propagates, not swallowed as 'init'.
	f = _write(tmp_path, "p.py", """\
		from dataclasses import dataclass
		from serde import serde
		import structlog
		log = structlog.get_logger()

		class FatalInit:
			@serde
			@dataclass
			class Config:
				tag: str

			def __init__(self, config):
				log.critical('init_fatal')

			def __call__(self, logger, method_name, event_dict):
				return event_dict
	""")
	with pytest.raises(typer.Exit):
		_construct(f, "FatalInit", {"tag": "x"})


def test_load_noconfig_class_init_fatal_propagates(logging_handler, tmp_path):
	# A no-config class whose __init__ calls log.fatal (typer.Exit) propagates.
	f = _write(tmp_path, "p.py", """\
		import structlog
		log = structlog.get_logger()

		class FatalInit:
			def __init__(self):
				log.critical('init_fatal')

			def __call__(self, logger, method_name, event_dict):
				return event_dict
	""")
	with pytest.raises(typer.Exit):
		_construct(f, "FatalInit")


def test_load_class_with_config_init_raises_fatal(logging_handler, tmp_path):
	# A config-bearing class whose __init__ raises is fatal.
	f = _write(tmp_path, "p.py", """\
		from dataclasses import dataclass
		from serde import serde

		class Bad:
			@serde
			@dataclass
			class Config:
				tag: str

			def __init__(self, config):
				raise RuntimeError('boom')

			def __call__(self, logger, method_name, event_dict):
				return event_dict
	""")
	with pytest.raises(typer.Exit):
		_construct(f, "Bad", {"tag": "x"})


# ---------------------------------------------------------------------------
# LoggingConfig.load — processor signature validation (structlog Processor shape)
# ---------------------------------------------------------------------------


def _sig_file(tmp_path, *, name="p.py", params="logger, method_name: str, event_dict: MutableMapping[str, Any]", ret="MutableMapping[str, Any]"):
	body = "return 'x'" if ret == "str" else "return event_dict"
	return _write(tmp_path, name, f"""\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		def proc({params}) -> {ret}:
			{body}
	""")


def _load_sig(f, *, include_default=True):
	return LoggingConfig(handlers=[_handler_config(f, "proc")], include_default=include_default).load()


def test_load_logging_accepts_parameterised_event_dict(logging_handler, tmp_path):
	_load_sig(_sig_file(tmp_path))
	assert logging_handler.failure is False


def test_load_logging_accepts_bare_dict_event_and_return(logging_handler, tmp_path):
	_load_sig(_sig_file(tmp_path, params="logger, method_name: str, event_dict: dict", ret="dict"))
	assert logging_handler.failure is False


def test_load_logging_accepts_bare_mutable_mapping_event(logging_handler, tmp_path):
	_load_sig(_sig_file(tmp_path, params="logger, method_name: str, event_dict: MutableMapping", ret="dict"))
	assert logging_handler.failure is False


def test_load_logging_accepts_parameterised_dict_event(logging_handler, tmp_path):
	_load_sig(_sig_file(tmp_path, params="logger, method_name: str, event_dict: dict[str, Any]", ret="dict"))
	assert logging_handler.failure is False


def test_load_logging_accepts_any_logger_annotation(logging_handler, tmp_path):
	_load_sig(_sig_file(tmp_path, params="logger: Any, method_name: str, event_dict: dict", ret="dict"))
	assert logging_handler.failure is False


def test_load_logging_terminal_accepts_str_return(logging_handler, tmp_path):
	# include_default false → the sole processor is terminal and must return str.
	_load_sig(_sig_file(tmp_path, ret="str"), include_default=False)
	assert logging_handler.failure is False


def test_load_logging_accepts_instance_validated_on_call(logging_handler, tmp_path):
	f = _write(tmp_path, "inst.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		class Proc:
			def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
				return event_dict

		proc = Proc()
	""")
	_load_sig(f)
	assert logging_handler.failure is False


def test_load_logging_rejects_wrong_arity(logging_handler, tmp_path):
	with pytest.raises(typer.Exit):
		_load_sig(_sig_file(tmp_path, params="logger, method_name: str"))


def test_load_logging_rejects_wrong_logger_annotation(logging_handler, tmp_path):
	with pytest.raises(typer.Exit):
		_load_sig(_sig_file(tmp_path, params="logger: int, method_name: str, event_dict: dict", ret="dict"))


def test_load_logging_rejects_wrong_method_annotation(logging_handler, tmp_path):
	with pytest.raises(typer.Exit):
		_load_sig(_sig_file(tmp_path, params="logger, method_name: int, event_dict: dict", ret="dict"))


def test_load_logging_rejects_non_mapping_event_annotation(logging_handler, tmp_path):
	with pytest.raises(typer.Exit):
		_load_sig(_sig_file(tmp_path, params="logger, method_name: str, event_dict: int", ret="dict"))


def test_load_logging_rejects_wrong_parameterised_event_annotation(logging_handler, tmp_path):
	# dict[str, int] is not EventDict-compatible (must be (str, Any)).
	with pytest.raises(typer.Exit):
		_load_sig(_sig_file(tmp_path, params="logger, method_name: str, event_dict: dict[str, int]", ret="dict"))


def test_load_logging_rejects_non_terminal_str_return(logging_handler, tmp_path):
	# include_default true → processor is non-terminal and must return an EventDict, not str.
	with pytest.raises(typer.Exit):
		_load_sig(_sig_file(tmp_path, ret="str"), include_default=True)


def test_load_logging_rejects_terminal_non_str_return(logging_handler, tmp_path):
	# include_default false → the terminal processor must return str, not an EventDict.
	with pytest.raises(typer.Exit):
		_load_sig(_sig_file(tmp_path, ret="dict"), include_default=False)


def test_load_logging_rejects_unresolved_annotation(logging_handler, tmp_path):
	f = _write(tmp_path, "u.py", """\
		from __future__ import annotations

		def proc(logger, method_name: str, event_dict: NotDefined) -> NotDefined:
			return event_dict
	""")
	with pytest.raises(typer.Exit):
		_load_sig(f)


def test_load_logging_accepts_processor_class(logging_handler, tmp_path):
	# A processor class is validated on its __call__ with self dropped (it is not constructed at load time).
	f = _write(tmp_path, "c.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		class Proc:
			def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
				return event_dict
	""")
	LoggingConfig(handlers=[_handler_config(f, "Proc")], include_default=True).load()
	assert logging_handler.failure is False


def test_load_logging_rejects_processor_class_wrong_arity(logging_handler, tmp_path):
	# self is dropped before counting, so a 2-arg __call__ is rejected as arity 1, not 2.
	f = _write(tmp_path, "c.py", """\
		from __future__ import annotations

		class Proc:
			def __call__(self, logger, method_name):
				return None
	""")
	with pytest.raises(typer.Exit):
		LoggingConfig(handlers=[_handler_config(f, "Proc")], include_default=True).load()


# ---------------------------------------------------------------------------
# LoggingConfig.load — classification, terminal renderer, no_renderers warn
# ---------------------------------------------------------------------------


def _processor_file(tmp_path, name="p.py", *, returns="dict"):
	ret = "str" if returns == "str" else "MutableMapping[str, Any]"
	body = "return 'x'" if returns == "str" else "return event_dict"
	return _write(tmp_path, name, f"""\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		def proc(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> {ret}:
			{body}
	""")


def test_load_logging_returns_processor_specs(logging_handler, tmp_path):
	f = _processor_file(tmp_path)
	cfg = LoggingConfig(handlers=[_handler_config(f, "proc")], include_default=True)
	processors, handlers = cfg.load()
	assert len(handlers) == 0
	# One processor spec, not yet constructed; the terminal ConsoleRenderer is added later by setup_logging.
	assert len(processors) == 1
	assert all(isinstance(p, LoggingPlugin) for p in processors)
	assert not any(isinstance(p.plugin, structlog.dev.ConsoleRenderer) for p in processors)


def test_load_logging_include_default_false_last_processor_terminal(logging_handler, tmp_path):
	first = _processor_file(tmp_path, "a.py", returns="dict")
	last = _processor_file(tmp_path, "b.py", returns="str")
	cfg = LoggingConfig(
		handlers=[_handler_config(first, "proc"), _handler_config(last, "proc")],
		include_default=False,
	)
	processors, handlers = cfg.load()
	assert len(handlers) == 0
	# Two processor specs in order; validation accepted the str-returning terminal under include_default false.
	assert len(processors) == 2


def test_load_logging_classifies_handler(logging_handler, tmp_path):
	hf = _write(tmp_path, "h.py", """\
		import logging
		class H(logging.Handler):
			def emit(self, record):
				pass
	""")
	cfg = LoggingConfig(handlers=[_handler_config(hf, "H")], include_default=True)
	processors, handlers = cfg.load()
	# The Handler subclass is classified as a handler spec; no processors.
	assert len(handlers) == 1
	assert issubclass(handlers[0].plugin, logging.Handler)
	assert len(processors) == 0


def test_load_logging_no_renderers_warn_empty(logging_handler, tmp_path):
	# include_default false, no processors, no handlers → warn no_renderers.
	cfg = LoggingConfig(handlers=[], include_default=False)
	processors, handlers = cfg.load()
	assert len(processors) == 0
	assert len(handlers) == 0
	# A warning is not an error.
	assert logging_handler.failure is False


def test_load_logging_include_default_false_handler_only_no_warn(logging_handler, tmp_path):
	# include_default false but a Handler-type entry exists → still no processors, one handler spec.
	hf = _write(tmp_path, "h.py", """\
		import logging
		class H(logging.Handler):
			def emit(self, record):
				pass
	""")
	cfg = LoggingConfig(handlers=[_handler_config(hf, "H")], include_default=False)
	processors, handlers = cfg.load()
	assert len(processors) == 0
	assert len(handlers) == 1
