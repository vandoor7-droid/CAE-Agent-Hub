package com.caeagenthub.comsol;

import java.util.Map;

interface BridgeBackend {
    Map<String, Object> handle(String method, Map<String, Object> params) throws Exception;
}
