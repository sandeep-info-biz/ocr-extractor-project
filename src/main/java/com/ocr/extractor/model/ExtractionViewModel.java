package com.ocr.extractor.model;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public final class ExtractionViewModel {
    private final String filename;
    private final String documentId;
    private final String tokenId;
    private final String mode;
    private final String documentUrl;
    private final Map<String, Object> extractedData;
    private final String source;

    public ExtractionViewModel(
        String filename,
        String documentId,
        String tokenId,
        String mode,
        String documentUrl,
        Map<String, Object> extractedData,
        String source
    ) {
        this.filename = filename;
        this.documentId = documentId;
        this.tokenId = tokenId;
        this.mode = mode;
        this.documentUrl = documentUrl;
        this.extractedData = Collections.unmodifiableMap(new LinkedHashMap<>(extractedData));
        this.source = source;
    }

    public String getFilename() {
        return filename;
    }

    public String getDocumentId() {
        return documentId;
    }

    public String getTokenId() {
        return tokenId;
    }

    public String getMode() {
        return mode;
    }

    public String getDocumentUrl() {
        return documentUrl;
    }

    public Map<String, Object> getExtractedData() {
        return extractedData;
    }

    public String getSource() {
        return source;
    }
}
