# -*- coding: utf-8 -*-
"""Create a parameterized 2.45 GHz coax-fed rectangular microstrip patch in AEDT."""

from __future__ import print_function

import os
import time
import traceback


DESIGN_NAME = "Patch_2p45GHz_Coax_CodexMCP"
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.getcwd()

ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
PROJECT_SAVE_PATH = os.environ.get(
    "AEDT_MCP_PATCH_PROJECT",
    os.path.join(ROOT_DIR, "aedt_projects", "patch_2p45ghz_coax.aedt"),
)


def msg(text, level=0):
    line = "[AEDT MCP Patch] " + str(text)
    try:
        oDesktop.AddMessage("", "", level, line)
    except Exception:
        pass
    print(line)


def ensure_dir(path):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)


def change_local_variables(oDesign, variables):
    for name, value in variables:
        prop = [
            "NAME:" + name,
            "PropType:=", "VariableProp",
            "UserDef:=", True,
            "Value:=", value,
        ]
        try:
            oDesign.ChangeProperty([
                "NAME:AllTabs",
                [
                    "NAME:LocalVariableTab",
                    ["NAME:PropServers", "LocalVariables"],
                    ["NAME:NewProps", prop],
                ],
            ])
        except Exception:
            oDesign.ChangeProperty([
                "NAME:AllTabs",
                [
                    "NAME:LocalVariableTab",
                    ["NAME:PropServers", "LocalVariables"],
                    ["NAME:ChangedProps", prop],
                ],
            ])


def clear_modeler_objects(oEditor):
    names = []
    for group in ("Solids", "Sheets", "Lines", "Unclassified"):
        try:
            for item in list(oEditor.GetObjectsInGroup(group)):
                if item not in names:
                    names.append(item)
        except Exception:
            pass
    if names:
        oEditor.Delete(["NAME:Selections", "Selections:=", ",".join(names)])


def delete_boundary(oDesign, name):
    try:
        oDesign.GetModule("BoundarySetup").DeleteBoundaries([name])
    except Exception:
        pass


def create_box(oEditor, name, material, x, y, z, dx, dy, dz, solve_inside=True, color="(132 132 193)"):
    return oEditor.CreateBox(
        [
            "NAME:BoxParameters",
            "XPosition:=", x,
            "YPosition:=", y,
            "ZPosition:=", z,
            "XSize:=", dx,
            "YSize:=", dy,
            "ZSize:=", dz,
        ],
        [
            "NAME:Attributes",
            "Name:=", name,
            "Flags:=", "",
            "Color:=", color,
            "Transparency:=", 0.35 if solve_inside else 0,
            "PartCoordinateSystem:=", "Global",
            "UDMId:=", "",
            "MaterialValue:=", '"' + material + '"',
            "SurfaceMaterialValue:=", '""',
            "SolveInside:=", solve_inside,
            "ShellElement:=", False,
            "ShellElementThickness:=", "0mm",
            "IsMaterialEditable:=", True,
            "UseMaterialAppearance:=", False,
            "IsLightweight:=", False,
        ],
    )


def create_cylinder(oEditor, name, material, x, y, z, radius, height, solve_inside=True, color="(255 128 0)"):
    return oEditor.CreateCylinder(
        [
            "NAME:CylinderParameters",
            "XCenter:=", x,
            "YCenter:=", y,
            "ZCenter:=", z,
            "Radius:=", radius,
            "Height:=", height,
            "WhichAxis:=", "Z",
            "NumSides:=", "0",
        ],
        [
            "NAME:Attributes",
            "Name:=", name,
            "Flags:=", "",
            "Color:=", color,
            "Transparency:=", 0.15 if solve_inside else 0,
            "PartCoordinateSystem:=", "Global",
            "UDMId:=", "",
            "MaterialValue:=", '"' + material + '"',
            "SurfaceMaterialValue:=", '""',
            "SolveInside:=", solve_inside,
            "ShellElement:=", False,
            "ShellElementThickness:=", "0mm",
            "IsMaterialEditable:=", True,
            "UseMaterialAppearance:=", False,
            "IsLightweight:=", False,
        ],
    )


def create_rectangle(oEditor, name, x, y, z, width, height, axis="Z", color="(128 255 255)"):
    return oEditor.CreateRectangle(
        [
            "NAME:RectangleParameters",
            "IsCovered:=", True,
            "XStart:=", x,
            "YStart:=", y,
            "ZStart:=", z,
            "Width:=", width,
            "Height:=", height,
            "WhichAxis:=", axis,
        ],
        [
            "NAME:Attributes",
            "Name:=", name,
            "Flags:=", "",
            "Color:=", color,
            "Transparency:=", 0.4,
            "PartCoordinateSystem:=", "Global",
            "UDMId:=", "",
            "MaterialValue:=", '"vacuum"',
            "SurfaceMaterialValue:=", '""',
            "SolveInside:=", True,
            "ShellElement:=", False,
            "ShellElementThickness:=", "0mm",
            "IsMaterialEditable:=", True,
            "UseMaterialAppearance:=", False,
            "IsLightweight:=", False,
        ],
    )


def subtract(oEditor, blank, tool, keep=False):
    oEditor.Subtract(
        [
            "NAME:Selections",
            "Blank Parts:=", blank,
            "Tool Parts:=", tool,
        ],
        [
            "NAME:SubtractParameters",
            "KeepOriginals:=", keep,
        ],
    )


def assign_perf_e(oDesign, name, objects):
    delete_boundary(oDesign, name)
    oModule = oDesign.GetModule("BoundarySetup")
    oModule.AssignPerfectE(
        [
            "NAME:" + name,
            "Objects:=", objects,
            "InfGroundPlane:=", False,
        ]
    )


def assign_radiation(oDesign, name, objects):
    delete_boundary(oDesign, name)
    oModule = oDesign.GetModule("BoundarySetup")
    oModule.AssignRadiation(
        [
            "NAME:" + name,
            "Objects:=", objects,
            "IsFssReference:=", False,
            "IsForPML:=", False,
        ]
    )


def assign_lumped_port(oDesign, oEditor):
    delete_boundary(oDesign, "Port1")
    oModule = oDesign.GetModule("BoundarySetup")
    face_ids = list(oEditor.GetFaceIDs("PortSheet"))
    if not face_ids:
        raise Exception("PortSheet has no selectable face IDs")
    oModule.AssignLumpedPort(
        [
            "NAME:Port1",
            "DoDeembed:=", False,
            "RenormalizeAllTerminals:=", True,
            "Faces:=", [int(face_ids[0])],
            [
                "NAME:Modes",
                [
                    "NAME:Mode1",
                    "ModeNum:=", 1,
                    "UseIntLine:=", True,
                    [
                        "NAME:IntLine",
                        "Coordinate System:=", "Global",
                        "Start:=", ["-6.55mm", "0mm", "-8mm"],
                        "End:=", ["-4.75mm", "0mm", "-8mm"],
                    ],
                    "AlignmentGroup:=", 0,
                    "CharImp:=", "Zpi",
                    "RenormImp:=", "50ohm",
                ],
            ],
            "ShowReporterFilter:=", False,
            "ReporterFilter:=", [True],
            "Impedance:=", "50ohm",
        ]
    )


def create_setup_and_sweep(oDesign):
    oModule = oDesign.GetModule("AnalysisSetup")
    try:
        oModule.DeleteSetups(["Setup1"])
    except Exception:
        pass
    oModule.InsertSetup(
        "HfssDriven",
        [
            "NAME:Setup1",
            "SolveType:=", "Single",
            "Frequency:=", "2.45GHz",
            "MaxDeltaS:=", 0.02,
            "UseMatrixConv:=", False,
            "MaximumPasses:=", 10,
            "MinimumPasses:=", 2,
            "MinimumConvergedPasses:=", 2,
            "PercentRefinement:=", 30,
            "IsEnabled:=", True,
            "BasisOrder:=", 1,
            "DoLambdaRefine:=", True,
            "DoMaterialLambda:=", True,
            "SetLambdaTarget:=", False,
            "Target:=", 0.3333,
            "UseMaxTetIncrease:=", False,
            "PortAccuracy:=", 2,
            "UseABCOnPort:=", False,
            "SetPortMinMaxTri:=", False,
        ],
    )
    try:
        oModule.InsertFrequencySweep(
            "Setup1",
            [
                "NAME:Sweep_2_to_3GHz",
                "IsEnabled:=", True,
                "RangeType:=", "LinearStep",
                "RangeStart:=", "2GHz",
                "RangeEnd:=", "3GHz",
                "RangeStep:=", "0.01GHz",
                "Type:=", "Interpolating",
                "SaveFields:=", True,
                "SaveRadFields:=", True,
                "InterpTolerance:=", 0.5,
                "InterpMaxSolns:=", 250,
                "InterpMinSolns:=", 0,
                "InterpMinSubranges:=", 1,
                "InterpUseS:=", True,
                "InterpUsePortImped:=", False,
                "InterpUsePropConst:=", True,
                "UseDerivativeConvergence:=", False,
                "InterpDerivTolerance:=", 0.2,
                "UseFullBasis:=", True,
                "EnforcePassivity:=", True,
                "PassivityErrorTolerance:=", 0.0001,
                "EnforceCausality:=", False,
            ],
        )
    except Exception:
        oModule.InsertFrequencySweep(
            "Setup1",
            [
                "NAME:Sweep_2_to_3GHz",
                "IsEnabled:=", True,
                "RangeType:=", "LinearStep",
                "RangeStart:=", "2GHz",
                "RangeEnd:=", "3GHz",
                "RangeStep:=", "0.01GHz",
                "Type:=", "Discrete",
                "SaveFields:=", True,
                "SaveRadFields:=", True,
            ],
        )


def create_far_field(oDesign):
    oModule = oDesign.GetModule("RadField")
    try:
        oModule.DeleteSetup(["InfiniteSphere1"])
    except Exception:
        pass
    oModule.InsertFarFieldSphereSetup(
        [
            "NAME:InfiniteSphere1",
            "UseCustomRadiationSurface:=", False,
            "ThetaStart:=", "0deg",
            "ThetaStop:=", "180deg",
            "ThetaStep:=", "5deg",
            "PhiStart:=", "-180deg",
            "PhiStop:=", "180deg",
            "PhiStep:=", "5deg",
            "UseLocalCS:=", False,
        ]
    )


def create_reports(oDesign):
    oModule = oDesign.GetModule("ReportSetup")
    for report_name in ["S11_dB", "GainTotal_3D"]:
        try:
            oModule.DeleteReports([report_name])
        except Exception:
            pass
    oModule.CreateReport(
        "S11_dB",
        "Modal Solution Data",
        "Rectangular Plot",
        "Setup1 : Sweep_2_to_3GHz",
        ["Domain:=", "Sweep"],
        ["Freq:=", ["All"]],
        ["X Component:=", "Freq", "Y Component:=", ["dB(S(Port1,Port1))"]],
    )
    try:
        oModule.CreateReport(
            "GainTotal_3D",
            "Far Fields",
            "3D Polar Plot",
            "Setup1 : LastAdaptive",
            ["Context:=", "InfiniteSphere1"],
            ["Freq:=", ["f0"], "Theta:=", ["All"], "Phi:=", ["All"]],
            ["X Component:=", "Theta", "Y Component:=", ["dB(GainTotal)"]],
        )
    except Exception as exc:
        msg("3D gain report creation deferred until after solve: " + str(exc), 1)


def create_field_plot_placeholders(oDesign):
    # The field overlays reference solved fields. They are created after the model
    # and setup exist; if AEDT refuses before a solution exists, record that clearly.
    try:
        oFields = oDesign.GetModule("FieldsReporter")
        try:
            oFields.CalcStack("clear")
        except Exception:
            pass
        msg("FieldsReporter is available. Create surface current and E-field slice plots after solving if AEDT requires solved fields.", 0)
    except Exception as exc:
        msg("FieldsReporter not available before solve: " + str(exc), 1)


def main():
    ensure_dir(PROJECT_SAVE_PATH)
    oDesktop.RestoreWindow()
    oProject = oDesktop.GetActiveProject()
    if oProject is None:
        project_names = []
        try:
            project_names = list(oDesktop.GetProjectList())
        except Exception:
            pass
        if project_names:
            oProject = oDesktop.SetActiveProject(project_names[0])
        else:
            oProject = oDesktop.NewProject()

    name = DESIGN_NAME
    oDesign = None
    try:
        active_design = oProject.GetActiveDesign()
        active_name = active_design.GetName()
        if active_name.startswith(DESIGN_NAME):
            oDesign = active_design
            name = active_name
    except Exception:
        pass
    if oDesign is None:
        design_names = []
        try:
            design_names = list(oProject.GetTopDesignList())
        except Exception:
            try:
                design_names = list(oProject.GetDesignList())
            except Exception:
                pass
        if name in design_names:
            oDesign = oProject.SetActiveDesign(name)
        else:
            oProject.InsertDesign("HFSS", name, "DrivenModal", "")
            try:
                oDesign = oProject.SetActiveDesign(name)
            except Exception:
                oDesign = oProject.GetActiveDesign()
                try:
                    active_name = oDesign.GetName()
                except Exception:
                    active_name = ""
                if active_name != name:
                    raise
    if oDesign is None:
        oDesign = oProject.GetActiveDesign()
    try:
        name = oDesign.GetName()
    except Exception:
        name = DESIGN_NAME
    oEditor = oDesign.SetActiveEditor("3D Modeler")
    try:
        oEditor.SetModelUnits(["NAME:Units Parameter", "Units:=", "mm", "Rescale:=", False])
    except Exception:
        pass
    clear_modeler_objects(oEditor)

    variables = [
        ("f0", "2.45GHz"),
        ("patch_L", "29.4mm"),
        ("patch_W", "37.3mm"),
        ("sub_L", "70mm"),
        ("sub_W", "80mm"),
        ("h_sub", "1.6mm"),
        ("cu_t", "0.035mm"),
        ("feed_x", "-7.2mm"),
        ("feed_y", "0mm"),
        ("pin_r", "0.65mm"),
        ("coax_outer_r", "2.1mm"),
        ("coax_shield_r", "2.45mm"),
        ("anti_pad_r", "1.2mm"),
        ("coax_len", "8mm"),
        ("air_xy", "110mm"),
        ("air_above", "45mm"),
        ("air_below", "18mm"),
        ("port_w", "0.45mm"),
    ]
    change_local_variables(oDesign, variables)

    create_box(oEditor, "Substrate", "FR4_epoxy", "-sub_L/2", "-sub_W/2", "0mm", "sub_L", "sub_W", "h_sub", True, "(80 160 80)")
    create_box(oEditor, "Patch", "copper", "-patch_L/2", "-patch_W/2", "h_sub", "patch_L", "patch_W", "cu_t", False, "(255 128 0)")
    create_box(oEditor, "Ground", "copper", "-sub_L/2", "-sub_W/2", "-cu_t", "sub_L", "sub_W", "cu_t", False, "(255 128 0)")
    create_cylinder(oEditor, "FeedPin", "copper", "feed_x", "feed_y", "-coax_len", "pin_r", "coax_len + h_sub", False, "(255 96 0)")
    create_cylinder(oEditor, "CoaxDielectric", "teflon_based", "feed_x", "feed_y", "-coax_len", "coax_outer_r", "coax_len - cu_t", True, "(220 220 220)")
    create_cylinder(oEditor, "CoaxOuterShield", "copper", "feed_x", "feed_y", "-coax_len", "coax_shield_r", "coax_len - cu_t", False, "(255 128 0)")
    create_cylinder(oEditor, "CoaxShieldHoleTool", "vacuum", "feed_x", "feed_y", "-coax_len - cu_t", "coax_outer_r", "coax_len + cu_t", True, "(255 0 0)")
    try:
        subtract(oEditor, "CoaxDielectric", "FeedPin", True)
        subtract(oEditor, "CoaxOuterShield", "CoaxShieldHoleTool", False)
        subtract(oEditor, "Substrate", "FeedPin", True)
    except Exception as exc:
        msg("Coax/substrate feed clearance subtraction failed. " + str(exc), 1)
    create_cylinder(oEditor, "GroundClearanceTool", "vacuum", "feed_x", "feed_y", "-2*cu_t", "anti_pad_r", "4*cu_t", True, "(255 0 0)")
    try:
        subtract(oEditor, "Ground", "GroundClearanceTool", False)
    except Exception as exc:
        msg("Ground clearance subtraction failed; continuing with solid ground. " + str(exc), 1)

    create_rectangle(oEditor, "PortSheet", "feed_x + pin_r", "feed_y - port_w/2", "-coax_len", "coax_shield_r - pin_r", "port_w", "Z", "(128 255 255)")
    create_rectangle(oEditor, "EFieldCut_XZ", "-sub_L/2", "0mm", "-coax_len", "sub_L", "air_above + air_below", "Y", "(128 128 255)")
    create_box(oEditor, "AirBox", "vacuum", "-air_xy/2", "-air_xy/2", "-air_below", "air_xy", "air_xy", "air_above + air_below", True, "(128 192 255)")

    assign_perf_e(oDesign, "PerfectE_Patch", ["Patch"])
    assign_perf_e(oDesign, "PerfectE_Ground", ["Ground"])
    assign_perf_e(oDesign, "PerfectE_FeedPin", ["FeedPin"])
    assign_perf_e(oDesign, "PerfectE_CoaxOuterShield", ["CoaxOuterShield"])
    assign_radiation(oDesign, "Radiation_AirBox", ["AirBox"])
    assign_lumped_port(oDesign, oEditor)
    create_setup_and_sweep(oDesign)
    create_far_field(oDesign)
    create_reports(oDesign)
    create_field_plot_placeholders(oDesign)

    oProject.SaveAs(PROJECT_SAVE_PATH, True)

    result = {
        "ok": True,
        "project": oProject.GetName(),
        "design": name,
        "saved_as": PROJECT_SAVE_PATH,
        "variables": dict(variables),
        "setup": "Setup1",
        "sweep": "Sweep_2_to_3GHz",
        "reports": ["S11_dB", "GainTotal_3D"],
        "notes": [
            "Parameterized patch_L, patch_W, h_sub, feed_x, feed_y.",
            "HFSS Driven Modal setup at 2.45 GHz with 2-3 GHz sweep.",
            "Surface current and E-field slice plots may require solved fields before final plot creation/export.",
        ],
    }
    msg("Created design " + name)
    return result


try:
    result = main()
except Exception:
    result = {"ok": False, "traceback": traceback.format_exc()}
    msg(result["traceback"], 2)
