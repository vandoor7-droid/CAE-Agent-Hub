package com.caeagenthub.comsol;

import java.util.LinkedHashMap;
import java.util.Map;

final class PlaceholderBackend implements BridgeBackend {
    private String activeModelTag = null;
    private String activeModelPath = null;
    private final Map<String, String> parameters = new LinkedHashMap<>();

    @Override
    public Map<String, Object> handle(String method, Map<String, Object> params) {
        switch (method) {
            case "connect":
                return ComsolBridge.mapOf("connected", true, "mode", "placeholder");
            case "newModel":
                activeModelTag = stringOrDefault(params.get("tag"), "Model");
                activeModelPath = null;
                return ComsolBridge.mapOf("activeModel", activeModelTag);
            case "openModel":
                activeModelPath = ComsolBridge.asString(params.get("path"));
                activeModelTag = "Model";
                return ComsolBridge.mapOf("activeModel", activeModelTag, "path", activeModelPath);
            case "saveModel":
                activeModelPath = ComsolBridge.asString(params.get("path"));
                return ComsolBridge.mapOf("saved", true, "path", activeModelPath);
            case "modelInfo":
                return modelInfo();
            case "listParameters":
                return ComsolBridge.mapOf("parameters", parameters);
            case "setParameter":
                parameters.put(ComsolBridge.asString(params.get("name")), ComsolBridge.asString(params.get("value")));
                return ComsolBridge.mapOf("parameters", parameters);
            case "listStudies":
                return ComsolBridge.mapOf("studies", new String[] {"std1"});
            case "runStudy":
                return ComsolBridge.mapOf("ran", true, "studyTag", stringOrDefault(params.get("studyTag"), "std1"));
            case "evaluateExpression":
                return ComsolBridge.mapOf("expression", params.get("expression"), "value", null, "mode", "placeholder");
            case "exportPlot":
            case "exportTable":
                return ComsolBridge.mapOf("exported", true, "path", params.get("path"), "mode", "placeholder");
            default:
                throw new IllegalArgumentException("unsupported bridge method: " + method);
        }
    }

    private Map<String, Object> modelInfo() {
        return ComsolBridge.mapOf(
            "activeModel", activeModelTag,
            "path", activeModelPath,
            "parameters", parameters,
            "studies", new String[] {"std1"},
            "datasets", new String[] {},
            "plots", new String[] {},
            "tables", new String[] {}
        );
    }

    private static String stringOrDefault(Object value, String fallback) {
        String text = ComsolBridge.asString(value);
        return text == null || text.isBlank() ? fallback : text;
    }
}
