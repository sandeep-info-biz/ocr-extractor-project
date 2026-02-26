package com.ocr.extractor.model;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public final class FetchDocumentViewModel {
    private final String documentId;
    private final String parserId;
    private final String status;
    private final String message;
    private final String filename;
    private final String code;
    private final String queueStatus;
    private final String documentUrl;
    private final String tokenId;
    private final Map<String, Object> parsedData;

    public FetchDocumentViewModel(
        String documentId,
        String parserId,
        String status,
        String message,
        String filename,
        String code,
        String queueStatus,
        String documentUrl,
        String tokenId,
        Map<String, Object> parsedData
    ) {
        this.documentId = documentId;
        this.parserId = parserId;
        this.status = status;
        this.message = message;
        this.filename = filename;
        this.code = code;
        this.queueStatus = queueStatus;
        this.documentUrl = documentUrl;
        this.tokenId = tokenId;
        this.parsedData = Collections.unmodifiableMap(new LinkedHashMap<>(parsedData));
    }

    public String getDocumentId() {
        return documentId;
    }

    public String getParserId() {
        return parserId;
    }

    public String getStatus() {
        return status;
    }

    public String getMessage() {
        return message;
    }

    public String getFilename() {
        return filename;
    }

    public String getCode() {
        return code;
    }

    public String getQueueStatus() {
        return queueStatus;
    }

    public String getDocumentUrl() {
        return documentUrl;
    }

    public String getTokenId() {
        return tokenId;
    }

    public Map<String, Object> getParsedData() {
        return parsedData;
    }

    public boolean isCompleted() {
        return "completed".equalsIgnoreCase(status) && !parsedData.isEmpty();
    }
}
