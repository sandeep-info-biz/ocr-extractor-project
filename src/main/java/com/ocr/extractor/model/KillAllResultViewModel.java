package com.ocr.extractor.model;

public record KillAllResultViewModel(
    int clearedJobs,
    int clearedHeartbeats,
    int failedActiveDocuments,
    String message
) {
}
