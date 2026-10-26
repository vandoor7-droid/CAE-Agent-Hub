"""Example MCP-side workflow for an already configured COMSOL bridge.

This file is intentionally illustrative; call the corresponding MCP tools from
Codex rather than importing this module directly.
"""

WORKFLOW = [
    ("comsol_detect_tool", {}),
    ("comsol_start_bridge_tool", {}),
    ("comsol_bridge_ping_tool", {}),
    ("comsol_connect_tool", {"host": "127.0.0.1", "port": 2036}),
    ("comsol_open_model_tool", {"path": r"C:\path\to\model.mph"}),
    ("comsol_set_parameter_tool", {"name": "L", "value": "25[mm]"}),
    ("comsol_run_study_tool", {"study_tag": "std1"}),
    ("comsol_export_plot_tool", {"plot_group": "pg1", "path": r"C:\path\to\exports\pg1.png"}),
    ("comsol_export_table_tool", {"table": "tbl1", "path": r"C:\path\to\exports\tbl1.csv"}),
    ("comsol_save_model_tool", {"path": r"C:\path\to\model_copy.mph"}),
]
