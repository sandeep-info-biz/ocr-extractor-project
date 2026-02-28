package com.ocr.extractor.service;

import com.ocr.extractor.model.FeedbackResultViewModel;
import com.ocr.extractor.model.FetchDocumentViewModel;
import com.ocr.extractor.model.KillAllResultViewModel;
import com.ocr.extractor.model.QueueSubmissionViewModel;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

@Service
public class JavaWorkflowService {
    private final JavaResumeExtractorService javaResumeExtractorService;
    private final ExecutorService workerPool = Executors.newFixedThreadPool(2);
    private final AtomicInteger datasetEntries = new AtomicInteger(0);
    private final Map<String, QueueState> queueByDocumentId = new ConcurrentHashMap<>();
    private final Map<String, String> tokenToDocumentId = new ConcurrentHashMap<>();

    public JavaWorkflowService(JavaResumeExtractorService javaResumeExtractorService) {
        this.javaResumeExtractorService = javaResumeExtractorService;
    }

    public QueueSubmissionViewModel submitToQueue(MultipartFile resumeFile, String parserId, String environment) {
        String resolvedParserId = StringUtils.hasText(parserId) ? parserId.trim() : defaultParserId();
        String resolvedEnvironment = StringUtils.hasText(environment) ? environment.trim() : defaultEnvironment();
        String documentId = UUID.randomUUID().toString();
        String jobId = UUID.randomUUID().toString();
        String filename = String.valueOf(resumeFile.getOriginalFilename());

        byte[] content;
        try {
            content = resumeFile.getBytes();
        } catch (IOException ex) {
            throw new IllegalStateException("Unable to read uploaded file.", ex);
        }

        QueueState state = new QueueState(
            documentId,
            jobId,
            resolvedParserId,
            resolvedEnvironment,
            filename,
            "queued",
            "Document queued for processing",
            "",
            new LinkedHashMap<>(),
            OffsetDateTime.now().toString()
        );
        queueByDocumentId.put(documentId, state);

        workerPool.submit(() -> processDocument(state, content, filename));

        return new QueueSubmissionViewModel(
            documentId,
            jobId,
            resolvedParserId,
            resolvedEnvironment,
            filename,
            "queued",
            "Document queued for processing"
        );
    }

    public FetchDocumentViewModel fetchDocument(String parserId, String documentId) {
        QueueState state = queueByDocumentId.get(documentId);
        if (state == null) {
            throw new IllegalStateException("document_id not found");
        }
        String status = state.status;
        String message = state.message;
        String code = "completed".equalsIgnoreCase(status) ? "document_retrieved" : "no_parsed_data";
        return new FetchDocumentViewModel(
            state.documentId,
            state.parserId,
            status,
            message,
            state.filename,
            code,
            status,
            "",
            state.tokenId,
            state.parsedData
        );
    }

    public FeedbackResultViewModel submitFeedback(String tokenId, Map<String, Object> correctedData, int rating, boolean retrainOnSubmit) {
        if (!StringUtils.hasText(tokenId)) {
            throw new IllegalStateException("token_id is missing.");
        }
        String documentId = tokenToDocumentId.get(tokenId);
        if (!StringUtils.hasText(documentId)) {
            throw new IllegalStateException("token_id not found");
        }
        QueueState state = queueByDocumentId.get(documentId);
        if (state == null) {
            throw new IllegalStateException("document_id not found");
        }
        if (correctedData != null && !correctedData.isEmpty()) {
            state.parsedData = new LinkedHashMap<>(correctedData);
            state.updatedAt = OffsetDateTime.now().toString();
            state.message = "Feedback saved";
            datasetEntries.incrementAndGet();
        }
        return new FeedbackResultViewModel(tokenId, rating, retrainOnSubmit, datasetEntries.get());
    }

    public KillAllResultViewModel killAllAndClearQueue() {
        int cleared = queueByDocumentId.size();
        queueByDocumentId.clear();
        tokenToDocumentId.clear();
        return new KillAllResultViewModel(
            cleared,
            0,
            0,
            "Cleared Java queue state"
        );
    }

    public String defaultParserId() {
        return "java-local";
    }

    public String defaultEnvironment() {
        return "dev";
    }

    private void processDocument(QueueState state, byte[] content, String filename) {
        try {
            state.status = "processing";
            state.message = "Document is currently processing";
            state.updatedAt = OffsetDateTime.now().toString();

            Map<String, Object> result = javaResumeExtractorService.extract(content, filename);
            @SuppressWarnings("unchecked")
            Map<String, Object> extractedData = (Map<String, Object>) result.getOrDefault("extracted_data", new LinkedHashMap<>());
            String tokenId = String.valueOf(result.getOrDefault("token_id", UUID.randomUUID().toString()));
            state.tokenId = tokenId;
            state.parsedData = extractedData;
            state.status = "completed";
            state.message = "Document processed successfully";
            state.updatedAt = OffsetDateTime.now().toString();
            tokenToDocumentId.put(tokenId, state.documentId);
        } catch (Exception ex) {
            state.status = "failed";
            state.message = "Processing failed: " + ex.getMessage();
            state.updatedAt = OffsetDateTime.now().toString();
        }
    }

    private static final class QueueState {
        private final String documentId;
        private final String jobId;
        private final String parserId;
        private final String environment;
        private final String filename;
        private volatile String status;
        private volatile String message;
        private volatile String tokenId;
        private volatile Map<String, Object> parsedData;
        private volatile String updatedAt;

        private QueueState(
            String documentId,
            String jobId,
            String parserId,
            String environment,
            String filename,
            String status,
            String message,
            String tokenId,
            Map<String, Object> parsedData,
            String updatedAt
        ) {
            this.documentId = documentId;
            this.jobId = jobId;
            this.parserId = parserId;
            this.environment = environment;
            this.filename = filename;
            this.status = status;
            this.message = message;
            this.tokenId = tokenId;
            this.parsedData = parsedData;
            this.updatedAt = updatedAt;
        }
    }
}
