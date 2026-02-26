package com.ocr.extractor.model;

public final class QueueSubmissionViewModel {
    private final String documentId;
    private final String jobId;
    private final String parserId;
    private final String environment;
    private final String filename;
    private final String status;
    private final String message;

    public QueueSubmissionViewModel(
        String documentId,
        String jobId,
        String parserId,
        String environment,
        String filename,
        String status,
        String message
    ) {
        this.documentId = documentId;
        this.jobId = jobId;
        this.parserId = parserId;
        this.environment = environment;
        this.filename = filename;
        this.status = status;
        this.message = message;
    }

    public String getDocumentId() {
        return documentId;
    }

    public String getJobId() {
        return jobId;
    }

    public String getParserId() {
        return parserId;
    }

    public String getEnvironment() {
        return environment;
    }

    public String getFilename() {
        return filename;
    }

    public String getStatus() {
        return status;
    }

    public String getMessage() {
        return message;
    }
}
