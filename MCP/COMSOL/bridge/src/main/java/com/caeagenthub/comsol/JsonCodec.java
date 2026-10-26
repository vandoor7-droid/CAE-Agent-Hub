package com.caeagenthub.comsol;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class JsonCodec {
    private JsonCodec() {}

    static Map<String, Object> parseObject(String text) {
        Parser parser = new Parser(text);
        Object value = parser.parseValue();
        parser.skipWhitespace();
        if (!parser.isEnd()) {
            throw new IllegalArgumentException("unexpected trailing JSON content");
        }
        if (!(value instanceof Map)) {
            throw new IllegalArgumentException("JSON payload must be an object");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> result = (Map<String, Object>) value;
        return result;
    }

    static String toJson(Object value) {
        StringBuilder builder = new StringBuilder();
        writeJson(builder, value);
        return builder.toString();
    }

    private static void writeJson(StringBuilder builder, Object value) {
        if (value == null) {
            builder.append("null");
        } else if (value instanceof String) {
            writeString(builder, (String) value);
        } else if (value instanceof Number || value instanceof Boolean) {
            builder.append(value);
        } else if (value instanceof Map) {
            builder.append('{');
            boolean first = true;
            for (Object entryObj : ((Map<?, ?>) value).entrySet()) {
                Map.Entry<?, ?> entry = (Map.Entry<?, ?>) entryObj;
                if (!first) {
                    builder.append(',');
                }
                writeString(builder, String.valueOf(entry.getKey()));
                builder.append(':');
                writeJson(builder, entry.getValue());
                first = false;
            }
            builder.append('}');
        } else if (value instanceof Iterable) {
            builder.append('[');
            boolean first = true;
            for (Object item : (Iterable<?>) value) {
                if (!first) {
                    builder.append(',');
                }
                writeJson(builder, item);
                first = false;
            }
            builder.append(']');
        } else if (value.getClass().isArray()) {
            builder.append('[');
            int length = java.lang.reflect.Array.getLength(value);
            for (int i = 0; i < length; i++) {
                if (i > 0) {
                    builder.append(',');
                }
                writeJson(builder, java.lang.reflect.Array.get(value, i));
            }
            builder.append(']');
        } else {
            writeString(builder, String.valueOf(value));
        }
    }

    private static void writeString(StringBuilder builder, String value) {
        builder.append('"');
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"':
                    builder.append("\\\"");
                    break;
                case '\\':
                    builder.append("\\\\");
                    break;
                case '\b':
                    builder.append("\\b");
                    break;
                case '\f':
                    builder.append("\\f");
                    break;
                case '\n':
                    builder.append("\\n");
                    break;
                case '\r':
                    builder.append("\\r");
                    break;
                case '\t':
                    builder.append("\\t");
                    break;
                default:
                    if (ch < 0x20) {
                        builder.append(String.format("\\u%04x", (int) ch));
                    } else {
                        builder.append(ch);
                    }
                    break;
            }
        }
        builder.append('"');
    }

    private static final class Parser {
        private final String text;
        private int index = 0;

        Parser(String text) {
            this.text = text == null ? "" : text;
        }

        boolean isEnd() {
            return index >= text.length();
        }

        void skipWhitespace() {
            while (!isEnd() && Character.isWhitespace(text.charAt(index))) {
                index++;
            }
        }

        Object parseValue() {
            skipWhitespace();
            if (isEnd()) {
                throw new IllegalArgumentException("empty JSON input");
            }
            char ch = text.charAt(index);
            if (ch == '"') {
                return parseString();
            }
            if (ch == '{') {
                return parseObjectValue();
            }
            if (ch == '[') {
                return parseArray();
            }
            if (ch == 't' && consume("true")) {
                return Boolean.TRUE;
            }
            if (ch == 'f' && consume("false")) {
                return Boolean.FALSE;
            }
            if (ch == 'n' && consume("null")) {
                return null;
            }
            if (ch == '-' || Character.isDigit(ch)) {
                return parseNumber();
            }
            throw new IllegalArgumentException("unexpected JSON token at position " + index);
        }

        private Map<String, Object> parseObjectValue() {
            expect('{');
            Map<String, Object> map = new LinkedHashMap<>();
            skipWhitespace();
            if (peek('}')) {
                index++;
                return map;
            }
            while (true) {
                skipWhitespace();
                String key = parseString();
                skipWhitespace();
                expect(':');
                Object value = parseValue();
                map.put(key, value);
                skipWhitespace();
                if (peek('}')) {
                    index++;
                    return map;
                }
                expect(',');
            }
        }

        private List<Object> parseArray() {
            expect('[');
            List<Object> list = new ArrayList<>();
            skipWhitespace();
            if (peek(']')) {
                index++;
                return list;
            }
            while (true) {
                list.add(parseValue());
                skipWhitespace();
                if (peek(']')) {
                    index++;
                    return list;
                }
                expect(',');
            }
        }

        private String parseString() {
            expect('"');
            StringBuilder builder = new StringBuilder();
            while (!isEnd()) {
                char ch = text.charAt(index++);
                if (ch == '"') {
                    return builder.toString();
                }
                if (ch != '\\') {
                    builder.append(ch);
                    continue;
                }
                if (isEnd()) {
                    throw new IllegalArgumentException("unterminated JSON escape");
                }
                char escaped = text.charAt(index++);
                switch (escaped) {
                    case '"':
                    case '\\':
                    case '/':
                        builder.append(escaped);
                        break;
                    case 'b':
                        builder.append('\b');
                        break;
                    case 'f':
                        builder.append('\f');
                        break;
                    case 'n':
                        builder.append('\n');
                        break;
                    case 'r':
                        builder.append('\r');
                        break;
                    case 't':
                        builder.append('\t');
                        break;
                    case 'u':
                        if (index + 4 > text.length()) {
                            throw new IllegalArgumentException("invalid unicode escape");
                        }
                        builder.append((char) Integer.parseInt(text.substring(index, index + 4), 16));
                        index += 4;
                        break;
                    default:
                        throw new IllegalArgumentException("invalid JSON escape: " + escaped);
                }
            }
            throw new IllegalArgumentException("unterminated JSON string");
        }

        private Number parseNumber() {
            int start = index;
            if (peek('-')) {
                index++;
            }
            while (!isEnd() && Character.isDigit(text.charAt(index))) {
                index++;
            }
            boolean floating = false;
            if (!isEnd() && text.charAt(index) == '.') {
                floating = true;
                index++;
                while (!isEnd() && Character.isDigit(text.charAt(index))) {
                    index++;
                }
            }
            if (!isEnd() && (text.charAt(index) == 'e' || text.charAt(index) == 'E')) {
                floating = true;
                index++;
                if (!isEnd() && (text.charAt(index) == '+' || text.charAt(index) == '-')) {
                    index++;
                }
                while (!isEnd() && Character.isDigit(text.charAt(index))) {
                    index++;
                }
            }
            String number = text.substring(start, index);
            return floating ? Double.parseDouble(number) : Long.parseLong(number);
        }

        private boolean consume(String token) {
            if (text.startsWith(token, index)) {
                index += token.length();
                return true;
            }
            return false;
        }

        private boolean peek(char expected) {
            return !isEnd() && text.charAt(index) == expected;
        }

        private void expect(char expected) {
            skipWhitespace();
            if (isEnd() || text.charAt(index) != expected) {
                throw new IllegalArgumentException("expected '" + expected + "' at position " + index);
            }
            index++;
        }
    }
}
