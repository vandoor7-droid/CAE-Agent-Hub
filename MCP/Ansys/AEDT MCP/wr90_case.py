from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_wr90_case(app: Any, output_dir: str | Path, solve: bool = True) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    project_name = app.project_name
    design_name = app.design_name
    project_path = output / f"{project_name}.aedt"
    app.modeler.model_units = "mm"

    width = 22.86
    height = 10.16
    length = 50.0
    wall = 2.0

    outer = app.modeler.create_box(
        [-(width / 2 + wall), -(height / 2 + wall), 0],
        [width + 2 * wall, height + 2 * wall, length],
        name="CopperWall",
        material="pec",
    )
    guide = app.modeler.create_box(
        [-width / 2, -height / 2, 0],
        [width, height, length],
        name="WaveguideVacuum",
        material="vacuum",
    )
    if not app.modeler.subtract(outer, guide, keep_originals=True):
        raise RuntimeError("failed to subtract the vacuum channel from the PEC body")

    end_faces = []
    for face in guide.faces:
        center = [float(value) for value in face.center]
        if abs(center[2]) < 1e-6 or abs(center[2] - length) < 1e-6:
            end_faces.append((center[2], face))
    end_faces.sort(key=lambda item: item[0])
    if len(end_faces) != 2:
        raise RuntimeError(f"expected two waveguide end faces, found {len(end_faces)}")

    port1 = app.wave_port(
        end_faces[0][1],
        modes=1,
        name="WavePort1",
        renormalize=False,
        characteristic_impedance="Zpi",
    )
    port2 = app.wave_port(
        end_faces[1][1],
        modes=1,
        name="WavePort2",
        renormalize=False,
        characteristic_impedance="Zpi",
    )
    if not port1 or not port2:
        raise RuntimeError("failed to create both wave ports")

    setup = app.create_setup("Setup1")
    setup.props["Frequency"] = "10GHz"
    setup.props["MaximumPasses"] = 6
    setup.props["MinimumPasses"] = 2
    setup.props["MinimumConvergedPasses"] = 1
    setup.props["MaxDeltaS"] = 0.02
    if not setup.update():
        raise RuntimeError("failed to update Setup1")

    sweep = app.create_linear_count_sweep(
        setup="Setup1",
        unit="GHz",
        start_frequency=8.0,
        stop_frequency=12.0,
        num_of_freq_points=81,
        name="Sweep8to12GHz",
        save_fields=False,
        sweep_type="Interpolating",
        interpolation_tol=0.5,
    )
    if not sweep:
        raise RuntimeError("failed to create the 8-12 GHz sweep")

    messages, valid = app.validate_full_design(output_dir=str(output), ports=2)
    if not valid:
        raise RuntimeError("HFSS validation failed: " + " | ".join(messages))
    if not app.save_project(project_path):
        raise RuntimeError(f"failed to save project to {project_path}")

    exported = []
    if solve:
        if not app.analyze_setup("Setup1", cores=2, blocking=True):
            raise RuntimeError("HFSS Setup1 solve failed")
        if not app.save_project(project_path):
            raise RuntimeError("failed to save solved project")
        profile_path = output / f"{project_name}.prof"
        convergence_path = output / f"{project_name}.conv"
        touchstone_path = output / f"{project_name}.s2p"
        if app.export_profile("Setup1", "", str(profile_path)):
            exported.append(str(profile_path))
        if app.export_convergence("Setup1", "", str(convergence_path)):
            exported.append(str(convergence_path))
        touchstone = app.export_touchstone(
            setup="Setup1",
            sweep="Sweep8to12GHz",
            output_file=str(touchstone_path),
            renormalization=False,
            gamma_impedance_comments=True,
        )
        if not touchstone:
            raise RuntimeError("failed to export modal-impedance Touchstone data")
        exported.append(str(Path(touchstone)))

    return {
        "success": True,
        "project": project_name,
        "design": design_name,
        "project_path": str(project_path),
        "setup": "Setup1",
        "sweep": "Sweep8to12GHz",
        "frequency_range_ghz": [8.0, 12.0],
        "solution_frequency_ghz": 10.0,
        "wr90_dimensions_mm": {"width": width, "height": height, "length": length},
        "ports": ["WavePort1", "WavePort2"],
        "touchstone_renormalized": False,
        "validation_messages": messages,
        "solved": solve,
        "exported_files": exported,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
