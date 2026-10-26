# encoding: utf-8
"""Mechanical-side mesh extraction and controlled property-update bridge.

Prepend a JSON-compatible ``REQUEST = {...}`` object and send this complete file
through the Workbench MCP main-context queue executor. The script prints one
``ANSYS_STRUCTURAL_JSON:`` marker line. It deliberately reports unsupported
Mechanical release properties instead of synthesizing values.
"""

from __future__ import print_function

import traceback


def _serializer():
    import clr
    clr.AddReference("System.Web.Extensions")
    from System.Web.Script.Serialization import JavaScriptSerializer
    return JavaScriptSerializer()


JSON = _serializer()


def _plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), _plain(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    try:
        return [_plain(item) for item in value]
    except Exception:
        return str(value)


def _get_first(obj, names):
    for name in names:
        try:
            value = getattr(obj, name)
            if callable(value):
                value = value()
            return _plain(value), name
        except Exception:
            pass
    return None, None


def _objects_by_name(name):
    try:
        return list(DataModel.GetObjectsByName(name))
    except Exception:
        try:
            return list(ExtAPI.DataModel.GetObjectsByName(name))
        except Exception:
            return []


def _require_one(name):
    objects = _objects_by_name(name)
    if len(objects) != 1:
        raise ValueError("expected exactly one object named %s; found %d" % (name, len(objects)))
    return objects[0]


def _session_state():
    payload = {"project_available": False, "model_available": False, "analysis_count": 0, "analyses": []}
    try:
        payload["project_available"] = ExtAPI.DataModel.Project is not None
        payload["project_directory"] = str(ExtAPI.DataModel.Project.ProjectDirectory)
    except Exception as exc:
        payload["project_error"] = str(exc)
    try:
        payload["model_available"] = Model is not None
        analyses = list(Model.Analyses)
        payload["analysis_count"] = len(analyses)
        payload["analyses"] = [str(item.Name) for item in analyses]
    except Exception as exc:
        payload["model_error"] = str(exc)
    return payload


def _analysis(request):
    analyses = list(Model.Analyses)
    requested = request.get("analysis_name")
    if requested:
        matches = [item for item in analyses if str(item.Name) == str(requested)]
        if len(matches) != 1:
            raise ValueError("analysis_name must match exactly one analysis")
        return matches[0]
    if len(analyses) != 1:
        raise ValueError("analysis_name is required when analysis_count is not one")
    return analyses[0]


def _mesh_data(analysis):
    for owner in (analysis, ExtAPI.DataModel.Project.Model):
        try:
            value = getattr(owner, "MeshData")
            if value is not None:
                return value
        except Exception:
            pass
    return None


def _metric_snapshot(name):
    metric = _require_one(name)
    result = {"name": name, "type": str(metric.GetType())}
    unsupported = []
    for output, candidates in (
        ("minimum", ["Minimum", "Min"]),
        ("maximum", ["Maximum", "Max"]),
        ("average", ["Average", "Mean"]),
        ("standard_deviation", ["StandardDeviation"]),
        ("histogram", ["HistogramData", "GetHistogramData"]),
        ("worst_element_ids", ["WorstElementIds", "MinimumElementIds", "MaximumElementIds"]),
    ):
        value, source = _get_first(metric, candidates)
        if source is None:
            unsupported.append(output)
        else:
            result[output] = value
            result[output + "_source_property"] = source
    result["unsupported"] = unsupported
    return result


def _element_centroids(mesh_data, element_ids):
    values = []
    if mesh_data is None:
        return values
    for element_id in element_ids or []:
        try:
            element = mesh_data.ElementById(int(element_id))
            node_ids = list(element.NodeIds)
            coordinates = []
            for node_id in node_ids:
                node = mesh_data.NodeById(int(node_id))
                coordinates.append([float(node.X), float(node.Y), float(node.Z)])
            count = float(len(coordinates))
            centroid = [sum(point[index] for point in coordinates) / count for index in range(3)]
            values.append({"id": int(element_id), "centroid": centroid})
        except Exception as exc:
            values.append({"id": int(element_id), "location_error": str(exc)})
    return values


def _snapshot(request):
    analysis = _analysis(request)
    mesh_data = _mesh_data(analysis)
    node_count, node_source = _get_first(mesh_data, ["NodeCount", "NodesCount"]) if mesh_data is not None else (None, None)
    element_count, element_source = _get_first(mesh_data, ["ElementCount", "ElementsCount"]) if mesh_data is not None else (None, None)
    metrics = [_metric_snapshot(name) for name in request.get("metric_object_names", [])]
    ids = []
    for metric in metrics:
        ids.extend(metric.get("worst_element_ids") or [])
    unsupported = []
    if node_source is None:
        unsupported.append("node_count")
    if element_source is None:
        unsupported.append("element_count")
    for metric in metrics:
        unsupported.extend([metric["name"] + "." + item for item in metric.get("unsupported", [])])
    return {
        "analysis_name": str(analysis.Name),
        "node_count": node_count,
        "element_count": element_count,
        "count_source_properties": {"nodes": node_source, "elements": element_source},
        "metrics": metrics,
        "worst_elements": _element_centroids(mesh_data, sorted(set([int(item) for item in ids]))),
        "unsupported_metrics": sorted(set(unsupported)),
    }


def _coerce(value):
    if not isinstance(value, dict):
        return value
    kind = value.get("kind")
    if kind == "quantity":
        return Quantity("%s [%s]" % (value["value"], value["unit"]))
    if kind == "integer":
        return int(value["value"])
    if kind == "float":
        return float(value["value"])
    if kind == "boolean":
        return bool(value["value"])
    raise ValueError("unsupported property value kind: %s" % kind)


def _apply_updates(request):
    readback = []
    for update in request.get("updates", []):
        obj = _require_one(update["object_name"])
        values = {}
        for property_name, raw in update.get("properties", {}).items():
            setattr(obj, property_name, _coerce(raw))
            values[property_name] = str(getattr(obj, property_name))
        readback.append({"object_name": update["object_name"], "properties": values})
    if request.get("clear_generated_data", True):
        try:
            Model.Mesh.ClearGeneratedData()
        except Exception:
            pass
    if request.get("generate_mesh", True):
        Model.Mesh.GenerateMesh()
    return {"updated": readback, "mesh_regenerated": bool(request.get("generate_mesh", True))}


def _dispatch(request):
    action = request.get("action")
    if action == "probe_session":
        return _session_state()
    if action == "mesh_snapshot":
        return _snapshot(request)
    if action == "apply_mesh_updates":
        return _apply_updates(request)
    if action == "generate_mesh":
        Model.Mesh.GenerateMesh()
        return {"mesh_regenerated": True}
    raise ValueError("unsupported action: %s" % action)


try:
    _payload = {"ok": True, "phase": str(REQUEST.get("action")), "session": _session_state(), "data": _dispatch(REQUEST), "warnings": [], "errors": []}
except Exception:
    _payload = {"ok": False, "phase": str(REQUEST.get("action") if "REQUEST" in globals() else "missing_request"), "session": _session_state(), "data": {}, "warnings": [], "errors": [traceback.format_exc()]}

print("ANSYS_STRUCTURAL_JSON:" + JSON.Serialize(_plain(_payload)))
