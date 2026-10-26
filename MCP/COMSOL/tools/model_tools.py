from __future__ import annotations

from pathlib import Path
from typing import Any

from .bridge_client import ComsolBridgeClient
from .detect import runs_dir


def ensure_path(path: str, suffix: str | None = None, must_exist: bool = True) -> Path:
    resolved = Path(path).expanduser().resolve()
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(resolved))
    if suffix and resolved.suffix.lower() != suffix.lower():
        raise ValueError(f"expected a {suffix} file: {resolved}")
    return resolved


def output_path(path: str | None, default_name: str) -> Path:
    if path:
        resolved = Path(path).expanduser().resolve()
    else:
        resolved = runs_dir() / default_name
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


class ComsolModelTools:
    def __init__(self, bridge: ComsolBridgeClient) -> None:
        self.bridge = bridge

    def connect(self, host: str = "127.0.0.1", port: int = 2036, username: str | None = None, password: str | None = None) -> dict[str, Any]:
        return self.bridge.request(
            "connect",
            {"host": host, "port": int(port), "username": username, "password": password},
        )

    def new_model(self, tag: str = "Model") -> dict[str, Any]:
        return self.bridge.request("newModel", {"tag": tag})

    def open_model(self, path: str) -> dict[str, Any]:
        model_path = ensure_path(path, suffix=".mph")
        return self.bridge.request("openModel", {"path": str(model_path)})

    def save_model(self, path: str | None = None) -> dict[str, Any]:
        save_path = output_path(path, "model_copy.mph") if path else None
        return self.bridge.request("saveModel", {"path": str(save_path) if save_path else None})

    def model_info(self) -> dict[str, Any]:
        return self.bridge.request("modelInfo")

    def list_parameters(self) -> dict[str, Any]:
        return self.bridge.request("listParameters")

    def set_parameter(self, name: str, value: str, description: str | None = None) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("parameter name is required")
        return self.bridge.request("setParameter", {"name": name, "value": value, "description": description})

    def list_studies(self) -> dict[str, Any]:
        return self.bridge.request("listStudies")

    def run_study(self, study_tag: str | None = None) -> dict[str, Any]:
        return self.bridge.request("runStudy", {"studyTag": study_tag})

    def evaluate(self, expression: str, dataset: str | None = None, unit: str | None = None) -> dict[str, Any]:
        if not expression.strip():
            raise ValueError("expression is required")
        return self.bridge.request("evaluateExpression", {"expression": expression, "dataset": dataset, "unit": unit})

    def export_plot(self, plot_group: str, path: str | None = None, width: int = 1600, height: int = 1000) -> dict[str, Any]:
        if not plot_group.strip():
            raise ValueError("plot_group is required")
        target = output_path(path, f"{plot_group}.png")
        return self.bridge.request(
            "exportPlot",
            {"plotGroup": plot_group, "path": str(target), "width": int(width), "height": int(height)},
        )

    def export_table(self, table: str, path: str | None = None) -> dict[str, Any]:
        if not table.strip():
            raise ValueError("table is required")
        target = output_path(path, f"{table}.csv")
        return self.bridge.request("exportTable", {"table": table, "path": str(target)})
