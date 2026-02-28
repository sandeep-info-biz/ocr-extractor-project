package com.ocr.extractor.controller;

import com.ocr.extractor.service.JavaResumeExtractorService;
import com.ocr.extractor.service.JavaWorkflowService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/java")
@Tag(name = "Java Resume REST", description = "Java-native resume extraction APIs (no Python dependency)")
public class ResumeRestController {
    private final JavaResumeExtractorService javaResumeExtractorService;
    private final JavaWorkflowService javaWorkflowService;

    public ResumeRestController(JavaResumeExtractorService javaResumeExtractorService, JavaWorkflowService javaWorkflowService) {
        this.javaResumeExtractorService = javaResumeExtractorService;
        this.javaWorkflowService = javaWorkflowService;
    }

    @GetMapping("/health")
    @Operation(summary = "Health check")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "backend", "java");
    }

    @GetMapping("/models")
    @Operation(summary = "Get Java extraction model info")
    public Map<String, Object> models() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "success");
        out.put("data", javaResumeExtractorService.loadMappingModelInfo());
        return out;
    }

    @PostMapping(value = "/extract", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Extract resume fields from file (Java-only)")
    public Map<String, Object> extract(@RequestParam("resume_file") MultipartFile resumeFile) {
        return javaResumeExtractorService.extract(resumeFile);
    }

    @PostMapping(value = "/queue/submit", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Submit resume to Java queue")
    public Map<String, Object> submitToQueue(
        @RequestParam("resume_file") MultipartFile resumeFile,
        @RequestParam(name = "parser_id", required = false) String parserId,
        @RequestParam(name = "environment", required = false) String environment
    ) {
        var queued = javaWorkflowService.submitToQueue(resumeFile, parserId, environment);
        return Map.of(
            "status", "success",
            "message", queued.getMessage(),
            "data", Map.of(
                "document_id", queued.getDocumentId(),
                "job_id", queued.getJobId(),
                "parser_id", queued.getParserId(),
                "environment", queued.getEnvironment(),
                "status", queued.getStatus()
            )
        );
    }

    @GetMapping("/queue/document/{documentId}")
    @Operation(summary = "Fetch queued Java document status/result")
    public Map<String, Object> fetchQueuedResult(
        @PathVariable("documentId") String documentId,
        @RequestParam(name = "parser_id", required = false) String parserId
    ) {
        var fetched = javaWorkflowService.fetchDocument(parserId == null ? javaWorkflowService.defaultParserId() : parserId, documentId);
        return Map.of(
            "status", "success",
            "code", fetched.getCode(),
            "message", fetched.getMessage(),
            "data", Map.of(
                "document_id", fetched.getDocumentId(),
                "parser_id", fetched.getParserId(),
                "status", fetched.getStatus(),
                "queue_status", fetched.getQueueStatus(),
                "token_id", fetched.getTokenId(),
                "parsed_data", fetched.getParsedData()
            )
        );
    }

    @PostMapping("/queue/feedback")
    @Operation(summary = "Submit feedback to Java queue workflow")
    public Map<String, Object> submitFeedback(@RequestBody Map<String, Object> payload) {
        String tokenId = String.valueOf(payload.getOrDefault("token_id", ""));
        int rating = 5;
        try {
            rating = Integer.parseInt(String.valueOf(payload.getOrDefault("rating", "5")));
        } catch (Exception ignored) {
            rating = 5;
        }
        boolean retrain = Boolean.parseBoolean(String.valueOf(payload.getOrDefault("retrain_on_submit", "true")));
        @SuppressWarnings("unchecked")
        Map<String, Object> corrected = payload.get("corrected_data") instanceof Map<?, ?> map
            ? (Map<String, Object>) map
            : new LinkedHashMap<>();
        var feedback = javaWorkflowService.submitFeedback(tokenId, corrected, rating, retrain);
        return Map.of(
            "status", "success",
            "message", "Feedback saved",
            "data", Map.of(
                "token_id", feedback.tokenId(),
                "rating", feedback.rating(),
                "retrained", feedback.retrained(),
                "total_dataset_entries", feedback.totalDatasetEntries()
            )
        );
    }
}
