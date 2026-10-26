from dataclasses import dataclass


class TargetValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AedtTarget:
    kind: str
    value: int

    def __post_init__(self) -> None:
        if self.kind not in {"pid", "port"}:
            raise TargetValidationError(f"unsupported AEDT target kind: {self.kind!r}")
        if type(self.value) is not int:
            raise TargetValidationError("AEDT target value must be an integer")
        if self.value <= 0:
            raise TargetValidationError("AEDT target value must be positive")
        if self.kind == "port" and self.value > 65535:
            raise TargetValidationError("AEDT target port must be at most 65535")

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.value}"

    @classmethod
    def from_values(
        cls, pid: int | None = None, port: int | None = None
    ) -> "AedtTarget":
        if (pid is None) == (port is None):
            raise TargetValidationError("exactly one AEDT PID or gRPC port is required")
        if pid is not None:
            return cls(kind="pid", value=pid)
        return cls(kind="port", value=port)
