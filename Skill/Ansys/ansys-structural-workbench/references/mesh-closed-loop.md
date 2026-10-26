# Mesh closed-loop contract

Use this loop only after geometry, connection scopes, and analysis purpose are validated.

## Loop

1. Create a baseline mesh plan with method, element order, global controls, critical regions, contact size targets, thickness layers, and fallback methods.
2. Generate the mesh through a main-context Mechanical Python request.
3. Extract a normalized snapshot containing body/node/element counts, invalid-element counts, metric distributions, contact size ratios, thickness layers, lost scopes, worst elements or worst regions, and current controls.
4. Run `evaluate_mesh_quality.py`.
5. If the status is `pass`, preserve the snapshot and continue to solve.
6. Otherwise wrap the snapshot with `attempt`, `max_attempts`, `method_policy`, and `repair_history`, then run `recommend_mesh_repairs.py`.
7. Apply only returned actions through `workbench_queue_execute_python_tool`, read settings back, clear/regenerate the mesh, and append the action/evidence to `repair_history`.
8. Stop when quality passes, the action is `stop`, the same failure persists after its targeted repair, or `max_attempts` is reached.

## Normalized loop input

```json
{
  "attempt": 1,
  "max_attempts": 3,
  "mesh": {
    "nonpositive_jacobian_count": 0,
    "zero_or_negative_volume_count": 0,
    "unmeshed_active_body_count": 0,
    "invalid_contact_scope_count": 0,
    "lost_control_scope_count": 0,
    "maximum_skewness": 0.93,
    "worst_skewness_in_critical_region": true,
    "low_quality_element_fraction": 0.002,
    "low_quality_elements_in_critical_region": true,
    "contact_size_ratios": [{"name": "C1", "ratio": 2.2}],
    "worst_elements": [{"id": 42, "region": "PIN_HOLE", "metric": "skewness", "value": 0.93}],
    "quality_gates": {}
  },
  "controls": {"growth_rate": 1.5, "method": "sweep"},
  "method_policy": {"prefer": ["sweep", "multizone"], "fallback": "patch_conforming_tetra"},
  "repair_history": []
}
```

## Approved actions

- `repair_scope`: restore invalid/lost control or contact scopes.
- `match_contact_sizing`: reduce opposing contact mesh-size ratio.
- `refine_worst_region`: add or tighten a local control around an identified region.
- `slow_transition`: reduce growth rate or add a transition zone.
- `increase_thickness_layers`: add through-thickness divisions when the profile requires them.
- `switch_method`: advance to the next configured method.
- `stop`: return evidence and do not solve.

Never automatically suppress geometry, remove contacts, change element dimensionality, or globally halve mesh size. Those actions require an updated mesh plan and engineering justification.

## Mechanical extraction expectations

Prefer public Mechanical scripting properties. Metric APIs vary by release, so probe available properties and return `unsupported_metrics` explicitly. Extract worst-element IDs and centroids when supported; otherwise identify the narrowest available body/face/region. The deterministic loop must not invent missing metric values.
