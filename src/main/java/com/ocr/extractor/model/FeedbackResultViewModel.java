package com.ocr.extractor.model;

public record FeedbackResultViewModel(
    String tokenId,
    int rating,
    boolean retrained,
    int totalDatasetEntries
) {
}
