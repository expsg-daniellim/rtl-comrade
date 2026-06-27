from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    """Runtime model for one selected test, constructed by load-model from a matched ModelConfigFileItem."""

    name:str
    filelist:list[str]
    path:str | None = None

    def get_model_name(self) -> str:
        """Return the model name."""

        return self.name

    def get_model_path(self) -> str | None:
        """Return the path to the models.yaml this model was loaded from."""

        return self.path

    def get_filelist(self) -> list[str]:
        """Return the model's HDL filelist."""

        return self.filelist
