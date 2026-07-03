from dataclasses import dataclass

from serde import serde, field


@serde
@dataclass
class RootRtlField:
	path:str = field(rename="reg-cfg-path")


@serde
@dataclass
class PlatformConfig:
	os:str
	unames:list[str]
	builder:str | None


@dataclass
class RootConfig:
	platforms:list[PlatformConfig]
	rtl_builder_cfgs:dict  # dict[str, RtlBuilderConfig] — typed once 01a lands
	cfg_rtl_reg:RootRtlField
