# Workbench MCP adapter

This adapter targets the repository server registered as `ansys-workbench` from `MCP/Ansys/Workbench MCP/server.py`. Do not substitute invented atomic tool names.

## Real tool map

| Logical operation | Real MCP tool | Input schema | Use |
|---|---|---|---|
| Detect installation | `workbench_detect_tool` | `{}` | Find RunWB2, PyMechanical, ANSYS root, job directory |
| Launch Workbench journal | `workbench_run_journal_tool` | `{journal_path, cwd?, batch?, extra_args?}` | Project/system creation, links, project-level updates |
| Launch Mechanical script | `mechanical_run_script_tool` | `{script_path, revision?, graphical?, project_file?, script_args?}` | Isolated scripted Mechanical run; not the live GUI session |
| Poll launched job | `workbench_job_status_tool` | `{job_id}` | Process state only; not solver validity |
| Read launched-job log | `workbench_job_log_tool` | `{job_id, stream?, tail_chars?}` | stdout/stderr evidence |
| List launched jobs | `workbench_list_jobs_tool` | `{limit?}` | Recover asynchronous job IDs |
| Inspect queue setup | `workbench_queue_install_info_tool` | `{}` | Locate main-context queue processor |
| List queue files | `workbench_queue_list_tool` | `{}` | Diagnose pending/stale requests |
| Submit raw queue request | `workbench_queue_submit_tool` | `{action, payload?}` | `ping`, `get_state`, or `execute_python` |
| Read queue response | `workbench_queue_response_tool` | `{request_id}` | Retrieve main-context stdout/errors |
| Queue ping | `workbench_queue_ping_tool` | `{wait_timeout?}` | Prove queue processor responsiveness |
| Queue state | `workbench_queue_state_tool` | `{wait_timeout?}` | Prove project/model/analysis state |
| Queue Python | `workbench_queue_execute_python_tool` | `{code, wait_timeout?}` | Preferred live Mechanical mutation path |
| Trigger queue from socket | `workbench_queue_process_with_socket_timer_tool` | `{timeout?}` | Recovery only; background execution may not be UI-thread safe |
| Socket ping | `workbench_socket_timer_ping_tool` | `{timeout?}` | Prove transport/bridge only |
| Socket state | `workbench_socket_timer_state_tool` | `{timeout?}` | Bridge metadata only; does not prove a loaded Model |
| Socket Python | `workbench_socket_timer_execute_python_tool` | `{code, timeout?}` | Compact read-only probes; mutation only after a live-version safety check |
| Stop socket bridge | `workbench_socket_timer_stop_tool` | `{timeout?}` | Explicit user-requested bridge shutdown |

## Proven-state ladder

Do not collapse these states:

```text
server tools listed
-> Workbench executable detected
-> socket or queue bridge responds
-> ExtAPI project exists
-> Model exists and analysis_count > 0
-> requested analysis is editable
-> mesh/results are current
-> requested final state converged and validated
```

Use `workbench_detect_tool`, then a bridge ping, then `workbench_queue_state_tool`. If the queue is not processing, use a short read-only socket Python probe that returns `Project is not None`, `Model is not None`, analysis names/count, and application version. A response with `has_extapi=true`, `has_model_symbol=true`, `Project_is_None=true`, or zero accessible analyses is not a usable Mechanical model session.

## Execution routing

1. Use `workbench_run_journal_tool` for Workbench systems, cell links, project open/save, and batch journals.
2. Use `workbench_queue_execute_python_tool` for live Mechanical tree mutation. The ACT queue processor executes on Mechanical's scripting/main context.
3. Use `workbench_socket_timer_execute_python_tool` for read-only discovery and compact state extraction. The v7 socket listener is a background thread; do not assume every Mechanical API is safe there.
4. Use `mechanical_run_script_tool` for an isolated project/script workflow when modifying the currently open GUI session is unnecessary.
5. Poll asynchronous jobs and read both stdout and stderr. A process exit is not a converged solve.

## Generic Python response contract

Live snippets must catch exceptions, print a single `ANSYS_STRUCTURAL_JSON:` line, and include:

```json
{
  "ok": true,
  "phase": "MESH_EXTRACT",
  "project_available": true,
  "model_available": true,
  "analysis_name": "Static Structural",
  "data": {},
  "warnings": [],
  "errors": []
}
```

The socket executor may also return `_result`; the queue executor currently returns stdout/stderr. Parse the marker from stdout for portability. Never depend on a raw DataModel object crossing the MCP boundary.

## Logical actions implemented through Python

`QUERY_TREE`, `QUERY_GEOMETRY`, `CREATE_NAMED_SELECTION`, `CONFIGURE_ANALYSIS`, `GENERATE_MESH`, `QUERY_MESH`, `APPLY_MESH_REPAIR`, `SOLVE`, `QUERY_RESULT`, `EXPORT_EVIDENCE`, and Mechanical-side `SAVE_PROJECT` are not separate MCP tools in this server. Implement them as idempotent Mechanical Python snippets sent through the queue, with names, scopes, settings, and read-back evidence returned as JSON.

Resolve objects by semantic names and validated properties. Do not use persistent topology IDs without revalidation. Save only after a passed gate or an explicit recovery checkpoint.

## Capability declaration

Record capability as `native`, `scripted`, `read_only`, or `unsupported`, not a boolean alone. Example:

```json
{
  "bridge_probe": "native",
  "live_mechanical_mutation": "scripted_main_queue",
  "mesh_generation": "scripted",
  "mesh_metric_distribution": "scripted_version_dependent",
  "worst_element_location": "scripted_version_dependent",
  "result_query": "scripted",
  "project_system_linking": "journal"
}
```

If a Mechanical release cannot expose metric distributions or worst-element IDs through the available scripting API, mark that gate `unsupported`; do not certify mesh quality from screenshots.
