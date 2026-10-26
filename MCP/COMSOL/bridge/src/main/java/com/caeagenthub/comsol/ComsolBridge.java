package com.caeagenthub.comsol;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public final class ComsolBridge {
    private final BridgeBackend backend;
    private boolean running = true;

    public ComsolBridge(BridgeBackend backend) {
        this.backend = backend;
    }

    public static void main(String[] args) throws Exception {
        BridgeBackend backend;
        if ("true".equalsIgnoreCase(System.getenv("COMSOL_MCP_PLACEHOLDER_BACKEND"))) {
            backend = new PlaceholderBackend();
        } else {
            backend = new ReflectiveComsolBackend();
        }
        new ComsolBridge(backend).run();
    }

    private void run() throws Exception {
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        PrintWriter writer = new PrintWriter(System.out, true, StandardCharsets.UTF_8);

        String line;
        while (running && (line = reader.readLine()) != null) {
            Map<String, Object> response = handleLine(line);
            writer.println(JsonCodec.toJson(response));
            writer.flush();
        }
    }

    private Map<String, Object> handleLine(String line) {
        String id = null;
        try {
            Map<String, Object> request = JsonCodec.parseObject(line);
            id = asString(request.get("id"));
            String method = asString(request.get("method"));
            Map<String, Object> params = asMap(request.get("params"));

            Map<String, Object> result;
            if ("ping".equals(method)) {
                result = mapOf("pong", true, "backend", backend.getClass().getSimpleName());
            } else if ("shutdown".equals(method)) {
                running = false;
                result = mapOf("shutdown", true);
            } else {
                result = backend.handle(method, params);
            }
            return envelope(id, true, result, null);
        } catch (Exception ex) {
            Throwable detail = ex;
            if (ex instanceof InvocationTargetException && ((InvocationTargetException) ex).getTargetException() != null) {
                detail = ((InvocationTargetException) ex).getTargetException();
            }
            String message = detail.getMessage();
            if (message == null || message.isBlank()) {
                message = detail.toString();
            }
            return envelope(id, false, null, mapOf("message", message, "type", detail.getClass().getName()));
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value == null) {
            return new LinkedHashMap<>();
        }
        if (!(value instanceof Map)) {
            throw new IllegalArgumentException("params must be an object");
        }
        return (Map<String, Object>) value;
    }

    static String asString(Object value) {
        if (value == null) {
            return null;
        }
        return String.valueOf(value);
    }

    static Map<String, Object> envelope(String id, boolean ok, Map<String, Object> result, Map<String, Object> error) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("id", id);
        response.put("ok", ok);
        if (ok) {
            response.put("result", result == null ? new LinkedHashMap<>() : result);
        } else {
            response.put("error", error == null ? mapOf("message", "unknown error") : error);
        }
        return response;
    }

    static Map<String, Object> mapOf(Object... items) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < items.length; i += 2) {
            map.put(String.valueOf(items[i]), items[i + 1]);
        }
        return map;
    }
}
