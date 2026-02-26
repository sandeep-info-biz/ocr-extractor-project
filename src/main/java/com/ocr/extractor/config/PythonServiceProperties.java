package com.ocr.extractor.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "python.service")
public record PythonServiceProperties(
    String baseUrl,
    int timeoutSeconds,
    String authToken,
    String defaultParserId,
    String defaultEnvironment
) {
}
