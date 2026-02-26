package com.ocr.extractor.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ocr.extractor.model.FeedbackResultViewModel;
import com.ocr.extractor.config.PythonServiceProperties;
import com.ocr.extractor.model.FetchDocumentViewModel;
import com.ocr.extractor.model.KillAllResultViewModel;
import com.ocr.extractor.model.QueueSubmissionViewModel;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class PythonResumeExtractorService {
    private final ObjectMapper objectMapper;
    private final RestClient restClient;
    private final PythonServiceProperties pythonServiceProperties;

    public PythonResumeExtractorService(PythonServiceProperties pythonServiceProperties, ObjectMapper objectMapper) {
        this.pythonServiceProperties = pythonServiceProperties;
        this.objectMapper = objectMapper;
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        int timeoutMs = Math.max(10, pythonServiceProperties.timeoutSeconds()) * 1000;
        requestFactory.setConnectTimeout(timeoutMs);
        requestFactory.setReadTimeout(timeoutMs);
        this.restClient = RestClient.builder()
            .baseUrl(pythonServiceProperties.baseUrl())
            .requestFactory(requestFactory)
            .build();
    }

    public QueueSubmissionViewModel submitToQueue(MultipartFile resumeFile, String parserId, String environment) {
        try {
            String resolvedParserId = StringUtils.hasText(parserId) ? parserId.trim() : defaultParserId();
            String resolvedEnvironment = StringUtils.hasText(environment) ? environment.trim() : defaultEnvironment();

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", new MultipartFileResource(resumeFile));
            body.add("environment", resolvedEnvironment);

            RestClient.RequestBodySpec req = restClient.post()
                .uri("/dapi/v1/parser/{parserId}/parse/async", resolvedParserId)
                .contentType(MediaType.MULTIPART_FORM_DATA);
            if (StringUtils.hasText(pythonServiceProperties.authToken())) {
                req = req.header(HttpHeaders.AUTHORIZATION, "Token " + pythonServiceProperties.authToken().trim());
            }

            String responseBody = req.body(body)
                .retrieve()
                .body(String.class);

            Map<String, Object> payload = objectMapper.readValue(responseBody, new TypeReference<>() {});
            Map<String, Object> data = readMap(payload.get("data"));
            return new QueueSubmissionViewModel(
                asString(data.get("document_id")),
                asString(data.get("job_id")),
                resolvedParserId,
                resolvedEnvironment,
                String.valueOf(resumeFile.getOriginalFilename()),
                asString(payload.getOrDefault("code", "document_queued")),
                asString(payload.getOrDefault("message", "Document queued for processing"))
            );
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Invalid JSON response from parser async endpoint.", e);
        } catch (IOException e) {
            throw new IllegalStateException("Unable to read uploaded file for async queue request.", e);
        } catch (Exception e) {
            throw new IllegalStateException("Queue submit failed: " + e.getMessage(), e);
        }
    }

    public FetchDocumentViewModel fetchDocument(String parserId, String documentId) {
        try {
            RestClient.RequestHeadersSpec<?> req = restClient.get()
                .uri("/dapi/v1/parser/{parserId}/document/{documentId}", parserId, documentId);
            if (StringUtils.hasText(pythonServiceProperties.authToken())) {
                req = req.header(HttpHeaders.AUTHORIZATION, "Token " + pythonServiceProperties.authToken().trim());
            }

            String responseBody = req.retrieve().body(String.class);
            Map<String, Object> payload = objectMapper.readValue(responseBody, new TypeReference<>() {});
            String code = asString(payload.get("code"));
            String message = asString(payload.get("message"));
            Map<String, Object> data = readMap(payload.get("data"));
            String status = asString(data.getOrDefault("status", "processing"));
            String documentUrl = absoluteUrl(asString(data.get("url")));
            Map<String, Object> metadata = readMap(data.get("metadata"));
            String filename = asString(metadata.get("filename"));
            Map<String, Object> queue = readMap(data.get("queue"));
            String queueStatus = asString(queue.get("status"));

            List<Object> entries = readList(data.get("entries"));
            Map<String, Object> parsedData = new LinkedHashMap<>();
            String tokenId = "";
            if (!entries.isEmpty() && entries.get(0) instanceof Map<?, ?> first) {
                parsedData = readMap(((Map<?, ?>) first).get("parsed_data"));
                tokenId = asString(((Map<?, ?>) first).get("token_id"));
            }

            return new FetchDocumentViewModel(
                documentId,
                parserId,
                status,
                message,
                filename,
                code,
                queueStatus,
                documentUrl,
                tokenId,
                parsedData
            );
        } catch (RestClientResponseException e) {
            throw new IllegalStateException("Fetch document failed: HTTP " + e.getStatusCode().value() + " " + safeBody(e.getResponseBodyAsString()), e);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Invalid JSON response from document fetch endpoint.", e);
        } catch (Exception e) {
            throw new IllegalStateException("Fetch document failed: " + e.getMessage(), e);
        }
    }

    public FeedbackResultViewModel submitFeedback(String tokenId, Map<String, Object> correctedData, int rating, boolean retrainOnSubmit) {
        try {
            Map<String, Object> normalized = normalizeFeedbackPayload(correctedData);
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("token_id", tokenId);
            payload.put("extracted_data", normalized);
            payload.put("rating", rating);
            payload.put("retrain_on_submit", retrainOnSubmit);

            RestClient.RequestBodySpec req = restClient.post()
                .uri("/feedback")
                .contentType(MediaType.APPLICATION_JSON);
            if (StringUtils.hasText(pythonServiceProperties.authToken())) {
                req = req.header(HttpHeaders.AUTHORIZATION, "Token " + pythonServiceProperties.authToken().trim());
            }

            String responseBody = req.body(payload)
                .retrieve()
                .body(String.class);
            Map<String, Object> data = objectMapper.readValue(responseBody, new TypeReference<>() {});
            return new FeedbackResultViewModel(
                asString(data.get("token_id")),
                toInt(data.get("rating"), rating),
                toBoolean(data.get("retrained"), false),
                toInt(data.get("total_dataset_entries"), 0)
            );
        } catch (RestClientResponseException e) {
            throw new IllegalStateException("Feedback submit failed: HTTP " + e.getStatusCode().value() + " " + safeBody(e.getResponseBodyAsString()), e);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Invalid JSON response from feedback endpoint.", e);
        } catch (Exception e) {
            throw new IllegalStateException("Feedback submit failed: " + e.getMessage(), e);
        }
    }

    public KillAllResultViewModel killAllAndClearQueue() {
        try {
            RestClient.RequestBodySpec req = restClient.post()
                .uri("/admin/kill-all-processes?stop_api=false&clear_state=true")
                .contentType(MediaType.APPLICATION_JSON);
            if (StringUtils.hasText(pythonServiceProperties.authToken())) {
                req = req.header(HttpHeaders.AUTHORIZATION, "Token " + pythonServiceProperties.authToken().trim());
            }
            String responseBody = req.retrieve().body(String.class);
            Map<String, Object> payload = objectMapper.readValue(responseBody, new TypeReference<>() {});
            Map<String, Object> data = readMap(payload.get("data"));
            return new KillAllResultViewModel(
                toInt(data.get("cleared_jobs"), 0),
                toInt(data.get("cleared_heartbeats"), 0),
                toInt(data.get("failed_active_documents"), 0),
                asString(payload.getOrDefault("message", "Kill all request completed"))
            );
        } catch (RestClientResponseException e) {
            throw new IllegalStateException("Kill all failed: HTTP " + e.getStatusCode().value() + " " + safeBody(e.getResponseBodyAsString()), e);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Invalid JSON response from kill-all endpoint.", e);
        } catch (Exception e) {
            throw new IllegalStateException("Kill all failed: " + e.getMessage(), e);
        }
    }

    public String defaultParserId() {
        String value = String.valueOf(pythonServiceProperties.defaultParserId());
        return StringUtils.hasText(value) ? value : "f92700";
    }

    public String defaultEnvironment() {
        String value = String.valueOf(pythonServiceProperties.defaultEnvironment());
        return StringUtils.hasText(value) ? value : "dev";
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (Map.Entry<?, ?> row : map.entrySet()) {
                out.put(String.valueOf(row.getKey()), row.getValue());
            }
            return out;
        }
        return new LinkedHashMap<>();
    }

    private List<Object> readList(Object value) {
        if (value instanceof List<?> list) {
            return (List<Object>) list;
        }
        return List.of();
    }

    private String asString(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private int toInt(Object value, int fallback) {
        try {
            if (value instanceof Number n) {
                return n.intValue();
            }
            return Integer.parseInt(asString(value));
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private boolean toBoolean(Object value, boolean fallback) {
        if (value instanceof Boolean b) {
            return b;
        }
        String raw = asString(value).toLowerCase();
        if ("true".equals(raw) || "1".equals(raw) || "yes".equals(raw)) {
            return true;
        }
        if ("false".equals(raw) || "0".equals(raw) || "no".equals(raw)) {
            return false;
        }
        return fallback;
    }

    private String safeBody(String body) {
        String text = asString(body).trim();
        if (text.isBlank()) {
            return "(empty response body)";
        }
        return text.length() > 260 ? text.substring(0, 260) + "..." : text;
    }

    private Map<String, Object> normalizeFeedbackPayload(Map<String, Object> input) {
        Map<String, Object> out = new LinkedHashMap<>();
        if (input != null) {
            out.putAll(input);
        }

        // Map async API field name to training schema field name.
        if (out.containsKey("gulf_experience") && !out.containsKey("gulf_expierence")) {
            out.put("gulf_expierence", out.get("gulf_experience"));
        }

        out.put("skills", normalizeStringList(out.get("skills"), "skill_name"));
        out.put("languages", normalizeStringList(out.get("languages"), "language"));
        out.put("education", normalizeEducation(out.get("education")));

        if (out.get("education_degree") == null && out.get("education") instanceof String s && !s.isBlank()) {
            out.put("education_degree", s);
            out.put("education", List.of());
        }

        normalizeStringField(out, "first_name");
        normalizeStringField(out, "last_name");
        normalizeStringField(out, "phone_number");
        normalizeStringField(out, "email");
        normalizeStringField(out, "date_of_birth");
        normalizeStringField(out, "gender");
        normalizeStringField(out, "religion");
        normalizeStringField(out, "marital_status");
        normalizeStringField(out, "nationality_country_name");
        normalizeStringField(out, "country_region");
        normalizeStringField(out, "city");
        normalizeStringField(out, "postal_code");
        normalizeStringField(out, "industry_type");
        normalizeStringField(out, "designation_or_position");
        normalizeStringField(out, "passport_number");
        normalizeStringField(out, "passport_expiry_date");
        normalizeStringField(out, "education_degree");
        normalizeStringField(out, "about_description_summary");
        normalizeStringField(out, "linkedin_url");
        normalizeStringField(out, "raw_text");

        out.put("gulf_expierence", toBoolean(out.get("gulf_expierence"), false));
        out.put("total_experience", normalizeIntOrNull(out.get("total_experience")));
        return out;
    }

    private void normalizeStringField(Map<String, Object> payload, String key) {
        if (!payload.containsKey(key)) {
            return;
        }
        Object value = payload.get(key);
        payload.put(key, value == null ? "" : String.valueOf(value));
    }

    private Integer normalizeIntOrNull(Object value) {
        if (value == null) return null;
        if (value instanceof Number n) return n.intValue();
        String s = asString(value).trim();
        if (s.isBlank()) return null;
        try {
            return Integer.parseInt(s.replaceAll("[^0-9-]", ""));
        } catch (Exception ignored) {
            return null;
        }
    }

    private List<String> normalizeStringList(Object value, String objectKeyHint) {
        if (!(value instanceof List<?> rows)) {
            return List.of();
        }
        List<String> out = new ArrayList<>();
        for (Object row : rows) {
            if (row == null) continue;
            if (row instanceof Map<?, ?> map) {
                Object nested = map.get(objectKeyHint);
                String text = asString(nested).trim();
                if (!text.isBlank()) out.add(text);
                continue;
            }
            String text = asString(row).trim();
            if (!text.isBlank()) out.add(text);
        }
        return out;
    }

    private List<Map<String, Object>> normalizeEducation(Object value) {
        if (!(value instanceof List<?> rows)) {
            return List.of();
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object row : rows) {
            if (!(row instanceof Map<?, ?> map)) {
                continue;
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("degree", asString(map.get("degree")));
            item.put("field_of_study", asString(map.get("field_of_study")));
            item.put("institution", asString(map.get("institution")));
            item.put("graduation_year", normalizeIntOrNull(map.get("graduation_year")));
            out.add(item);
        }
        return out;
    }

    private String absoluteUrl(String url) {
        if (!StringUtils.hasText(url)) {
            return "";
        }
        String trimmed = url.trim();
        if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
            return trimmed;
        }
        String base = String.valueOf(pythonServiceProperties.baseUrl());
        if (!StringUtils.hasText(base)) {
            return trimmed;
        }
        if (base.endsWith("/") && trimmed.startsWith("/")) {
            return base.substring(0, base.length() - 1) + trimmed;
        }
        if (!base.endsWith("/") && !trimmed.startsWith("/")) {
            return base + "/" + trimmed;
        }
        return base + trimmed;
    }
}
