package com.caeagenthub.comsol;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

final class ReflectiveComsolBackend implements BridgeBackend {
    private Class<?> modelUtilClass = null;
    private Object model = null;
    private String activeModelPath = null;

    @Override
    public Map<String, Object> handle(String method, Map<String, Object> params) throws Exception {
        switch (method) {
            case "connect":
                return connect(params);
            case "newModel":
                return newModel(params);
            case "openModel":
                return openModel(params);
            case "saveModel":
                return saveModel(params);
            case "modelInfo":
                return modelInfo();
            case "listParameters":
                return listParameters();
            case "setParameter":
                return setParameter(params);
            case "listStudies":
                return listStudies();
            case "runStudy":
                return runStudy(params);
            case "evaluateExpression":
                return evaluateExpression(params);
            case "exportPlot":
                return exportPlot(params);
            case "exportTable":
                return exportTable(params);
            default:
                throw new IllegalArgumentException("unsupported bridge method: " + method);
        }
    }

    private Class<?> modelUtil() throws ClassNotFoundException {
        if (modelUtilClass == null) {
            modelUtilClass = Class.forName("com.comsol.model.util.ModelUtil");
        }
        return modelUtilClass;
    }

    private Map<String, Object> connect(Map<String, Object> params) throws Exception {
        Class<?> util = modelUtil();
        String host = stringOrDefault(params.get("host"), "127.0.0.1");
        int port = intOrDefault(params.get("port"), 2036);
        String username = ComsolBridge.asString(params.get("username"));
        String password = ComsolBridge.asString(params.get("password"));

        if (username != null && password != null) {
            invokeStatic(util, "connect", host, port, username, password);
        } else {
            invokeStatic(util, "connect", host, port);
        }
        return ComsolBridge.mapOf("connected", true, "host", host, "port", port);
    }

    private Map<String, Object> newModel(Map<String, Object> params) throws Exception {
        Class<?> util = modelUtil();
        String tag = stringOrDefault(params.get("tag"), "Model");
        model = invokeStatic(util, "create", tag);
        activeModelPath = null;
        return ComsolBridge.mapOf("activeModel", tag);
    }

    private Map<String, Object> openModel(Map<String, Object> params) throws Exception {
        Class<?> util = modelUtil();
        String path = required(params, "path");
        try {
            model = invokeStatic(util, "load", path);
        } catch (NoSuchMethodException first) {
            model = invokeStatic(util, "load", "Model", path);
        }
        activeModelPath = path;
        return ComsolBridge.mapOf("activeModel", modelTag(), "path", activeModelPath);
    }

    private Map<String, Object> saveModel(Map<String, Object> params) throws Exception {
        requireModel();
        String path = ComsolBridge.asString(params.get("path"));
        if (path == null || path.isBlank()) {
            invoke(model, "save");
        } else {
            invoke(model, "save", path);
            activeModelPath = path;
        }
        return ComsolBridge.mapOf("saved", true, "path", activeModelPath);
    }

    private Map<String, Object> modelInfo() throws Exception {
        requireModel();
        return ComsolBridge.mapOf(
            "activeModel", modelTag(),
            "path", activeModelPath,
            "parameters", listParameters().get("parameters"),
            "studies", listTags(invoke(model, "study")),
            "datasets", listResultChildTags("dataset"),
            "plots", listResultChildTags("pg"),
            "tables", listResultChildTags("table")
        );
    }

    private Map<String, Object> listParameters() throws Exception {
        requireModel();
        Object param = invoke(model, "param");
        Map<String, Object> values = new LinkedHashMap<>();
        Object names = invoke(param, "varnames");
        for (String name : asStringArray(names)) {
            Object value = invoke(param, "get", name);
            values.put(name, value == null ? null : String.valueOf(value));
        }
        return ComsolBridge.mapOf("parameters", values);
    }

    private Map<String, Object> setParameter(Map<String, Object> params) throws Exception {
        requireModel();
        String name = required(params, "name");
        String value = required(params, "value");
        String description = ComsolBridge.asString(params.get("description"));
        Object param = invoke(model, "param");
        if (description == null || description.isBlank()) {
            invoke(param, "set", name, value);
        } else {
            invoke(param, "set", name, value, description);
        }
        return listParameters();
    }

    private Map<String, Object> listStudies() throws Exception {
        requireModel();
        return ComsolBridge.mapOf("studies", listTags(invoke(model, "study")));
    }

    private Map<String, Object> runStudy(Map<String, Object> params) throws Exception {
        requireModel();
        String tag = ComsolBridge.asString(params.get("studyTag"));
        Object study = invoke(model, "study");
        Object target = tag == null || tag.isBlank() ? invoke(study, "get", firstTag(study)) : invoke(study, "get", tag);
        invoke(target, "run");
        return ComsolBridge.mapOf("ran", true, "studyTag", tag);
    }

    private Map<String, Object> evaluateExpression(Map<String, Object> params) throws Exception {
        requireModel();
        String expression = required(params, "expression");
        Object result = invoke(model, "result");
        Object numerical = invoke(result, "numerical");
        Object eval = invoke(numerical, "create", "mcp_eval", "EvalGlobal");
        invoke(eval, "set", "expr", new String[] {expression});
        Object value = invoke(eval, "getReal");
        return ComsolBridge.mapOf("expression", expression, "value", stringifyArray(value));
    }

    private Map<String, Object> exportPlot(Map<String, Object> params) throws Exception {
        requireModel();
        String plotGroup = required(params, "plotGroup");
        String path = required(params, "path");
        Object result = invoke(model, "result");
        Object export = invoke(result, "export");
        Object image = invoke(export, "create", "mcp_plot_export", "Image");
        invoke(image, "set", "plotgroup", plotGroup);
        invoke(image, "set", "pngfilename", path);
        invoke(image, "run");
        return ComsolBridge.mapOf("exported", true, "path", path, "plotGroup", plotGroup);
    }

    private Map<String, Object> exportTable(Map<String, Object> params) throws Exception {
        requireModel();
        String table = required(params, "table");
        String path = required(params, "path");
        Object result = invoke(model, "result");
        Object export = invoke(result, "export");
        Object data = invoke(export, "create", "mcp_table_export", "Data");
        invoke(data, "set", "data", table);
        invoke(data, "set", "filename", path);
        invoke(data, "run");
        return ComsolBridge.mapOf("exported", true, "path", path, "table", table);
    }

    private Object listResultChildTags(String child) throws Exception {
        Object result = invoke(model, "result");
        return listTags(invoke(result, child));
    }

    private String modelTag() {
        try {
            Object tag = invoke(model, "tag");
            return tag == null ? null : String.valueOf(tag);
        } catch (Exception ignored) {
            return null;
        }
    }

    private void requireModel() {
        if (model == null) {
            throw new IllegalStateException("no active COMSOL model; call newModel or openModel first");
        }
    }

    private static String firstTag(Object collection) throws Exception {
        String[] tags = asStringArray(invoke(collection, "tags"));
        if (tags.length == 0) {
            throw new IllegalStateException("no studies are available");
        }
        return tags[0];
    }

    private static Object listTags(Object collection) throws Exception {
        return asStringArray(invoke(collection, "tags"));
    }

    private static Object invokeStatic(Class<?> target, String method, Object... args) throws Exception {
        return invokeOn(null, target, method, args);
    }

    private static Object invoke(Object target, String method, Object... args) throws Exception {
        return invokeOn(target, target.getClass(), method, args);
    }

    private static Object invokeOn(Object target, Class<?> type, String method, Object... args) throws Exception {
        for (Method candidate : type.getMethods()) {
            if (!candidate.getName().equals(method) || candidate.getParameterCount() != args.length) {
                continue;
            }
            try {
                return candidate.invoke(target, args);
            } catch (IllegalArgumentException ignored) {
                // Try the next overload.
            }
        }
        throw new NoSuchMethodException(type.getName() + "." + method + "/" + args.length);
    }

    private static String[] asStringArray(Object value) {
        if (value instanceof String[]) {
            return (String[]) value;
        }
        if (value instanceof Object[]) {
            return Arrays.stream((Object[]) value).map(String::valueOf).toArray(String[]::new);
        }
        return new String[0];
    }

    private static Object stringifyArray(Object value) {
        if (value == null) {
            return null;
        }
        if (value.getClass().isArray()) {
            if (value instanceof double[]) {
                return Arrays.toString((double[]) value);
            }
            if (value instanceof double[][]) {
                return Arrays.deepToString((double[][]) value);
            }
            if (value instanceof Object[]) {
                return Arrays.deepToString((Object[]) value);
            }
        }
        return String.valueOf(value);
    }

    private static String required(Map<String, Object> params, String key) {
        String value = ComsolBridge.asString(params.get(key));
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(key + " is required");
        }
        return value;
    }

    private static String stringOrDefault(Object value, String fallback) {
        String text = ComsolBridge.asString(value);
        return text == null || text.isBlank() ? fallback : text;
    }

    private static int intOrDefault(Object value, int fallback) {
        if (value == null) {
            return fallback;
        }
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        return Integer.parseInt(String.valueOf(value));
    }
}
