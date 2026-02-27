package com.ocr.extractor.controller;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ocr.extractor.model.ExtractionViewModel;
import com.ocr.extractor.model.FeedbackResultViewModel;
import com.ocr.extractor.model.FetchDocumentViewModel;
import com.ocr.extractor.model.HistoryItemViewModel;
import com.ocr.extractor.model.KillAllResultViewModel;
import com.ocr.extractor.model.QueueSubmissionViewModel;
import com.ocr.extractor.service.PythonResumeExtractorService;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.multipart.MultipartFile;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Controller
public class WebController {
    private static final String SESSION_LOGIN_TOKEN = "pythonAccessToken";
    private static final String SESSION_LOGIN_USER = "loggedInUser";
    private static final String SESSION_QUEUE_ITEMS = "queueItems";
    private static final String SESSION_HISTORY = "historyItems";
    private static final String SESSION_RESULTS = "resultItems";
    private static final String SESSION_EXPANDED_RESULT_ID = "expandedResultDocumentId";

    private final PythonResumeExtractorService pythonResumeExtractorService;
    private final ObjectMapper objectMapper;
    private final String uiLoginUser;
    private final String uiLoginPassword;

    public WebController(
        PythonResumeExtractorService pythonResumeExtractorService,
        ObjectMapper objectMapper,
        @Value("${app.login.username:}") String uiLoginUser,
        @Value("${app.login.password:}") String uiLoginPassword
    ) {
        this.pythonResumeExtractorService = pythonResumeExtractorService;
        this.objectMapper = objectMapper;
        if (uiLoginUser == null || uiLoginUser.isBlank() || uiLoginPassword == null || uiLoginPassword.isBlank()) {
            throw new IllegalStateException("APP_LOGIN_USERNAME and APP_LOGIN_PASSWORD must be configured.");
        }
        this.uiLoginUser = uiLoginUser;
        this.uiLoginPassword = uiLoginPassword;
    }

    @GetMapping("/")
    public String index(Model model, HttpSession session) {
        applySharedModel(model, session, pythonResumeExtractorService.defaultParserId(), pythonResumeExtractorService.defaultEnvironment());
        return "index";
    }

    @GetMapping("/history")
    public String history(Model model, HttpSession session) {
        if (session.getAttribute(SESSION_LOGIN_TOKEN) == null) {
            applySharedModel(model, session, pythonResumeExtractorService.defaultParserId(), pythonResumeExtractorService.defaultEnvironment());
            model.addAttribute("error", "Session expired. Please login again.");
            return "index";
        }
        applySharedModel(model, session, pythonResumeExtractorService.defaultParserId(), pythonResumeExtractorService.defaultEnvironment());
        return "history";
    }

    @PostMapping("/login")
    public String login(
        @RequestParam("username") String username,
        @RequestParam("password") String password,
        Model model,
        HttpSession session
    ) {
        try {
            if (!uiLoginUser.equals(username) || !uiLoginPassword.equals(password)) {
                throw new IllegalStateException("Invalid username or password.");
            }
            session.setAttribute(SESSION_LOGIN_TOKEN, "local-session");
            session.setAttribute(SESSION_LOGIN_USER, username);
            model.addAttribute("loginMessage", "Logged in successfully.");
        } catch (Exception ex) {
            model.addAttribute("error", ex.getMessage());
        }
        applySharedModel(model, session, pythonResumeExtractorService.defaultParserId(), pythonResumeExtractorService.defaultEnvironment());
        return "index";
    }

    @PostMapping("/logout")
    public String logout(Model model, HttpSession session) {
        session.removeAttribute(SESSION_LOGIN_TOKEN);
        session.removeAttribute(SESSION_LOGIN_USER);
        session.removeAttribute(SESSION_QUEUE_ITEMS);
        session.removeAttribute(SESSION_RESULTS);
        model.addAttribute("loginMessage", "Logged out.");
        applySharedModel(model, session, pythonResumeExtractorService.defaultParserId(), pythonResumeExtractorService.defaultEnvironment());
        return "index";
    }

    @PostMapping("/extract")
    public String submitToQueue(
        @RequestParam("resumeFile") MultipartFile resumeFile,
        @RequestParam(name = "parserId", required = false) String parserId,
        @RequestParam(name = "environment", required = false) String environment,
        Model model,
        HttpSession session
    ) {
        try {
            requireLogin(session);
            QueueSubmissionViewModel queued = pythonResumeExtractorService.submitToQueue(resumeFile, parserId, environment);
            upsertQueueItem(session, queued);
            model.addAttribute("queueMessage", queued.getMessage());
        } catch (Exception ex) {
            model.addAttribute("error", ex.getMessage());
        }
        applySharedModel(
            model,
            session,
            parserId == null || parserId.isBlank() ? pythonResumeExtractorService.defaultParserId() : parserId,
            environment == null || environment.isBlank() ? pythonResumeExtractorService.defaultEnvironment() : environment
        );
        return "index";
    }

    @PostMapping("/fetch")
    public String fetchQueuedResult(
        @RequestParam("documentId") String documentId,
        @RequestParam("parserId") String parserId,
        Model model,
        HttpSession session
    ) {
        try {
            requireLogin(session);
            FetchDocumentViewModel fetched = pythonResumeExtractorService.fetchDocument(parserId, documentId);
            model.addAttribute("queueMessage", fetched.getMessage());
            if (fetched.isCompleted()) {
                removeQueueItem(session, documentId);
            } else {
                touchQueueItem(session, documentId, parserId, fetched.getStatus(), fetched.getMessage(), fetched.getFilename());
            }
            if (fetched.isCompleted()) {
                upsertResultItem(
                    session,
                    fetched.getDocumentId(),
                    parserId,
                    fetched.getFilename(),
                    prettyJson(fetched.getParsedData()),
                    "",
                    fetched.getTokenId(),
                    fetched.getDocumentUrl()
                );
                session.setAttribute(SESSION_EXPANDED_RESULT_ID, fetched.getDocumentId());
            } else {
                model.addAttribute("queueMessage", fetched.getMessage());
            }
        } catch (Exception ex) {
            model.addAttribute("error", ex.getMessage());
        }
        applySharedModel(model, session, parserId, pythonResumeExtractorService.defaultEnvironment());
        return "index";
    }

    @PostMapping("/feedback")
    public String submitFeedback(
        @RequestParam("documentId") String documentId,
        @RequestParam("parserId") String parserId,
        @RequestParam("tokenId") String tokenId,
        @RequestParam("rating") int rating,
        @RequestParam("correctedJson") String correctedJson,
        @RequestParam(name = "retrainOnSubmit", defaultValue = "true") boolean retrainOnSubmit,
        Model model,
        HttpSession session
    ) {
        try {
            requireLogin(session);
            if (tokenId == null || tokenId.isBlank()) {
                throw new IllegalStateException("token_id is missing. Fetch completed data first.");
            }
            Map<String, Object> correctedData = parseJsonMap(correctedJson);
            FeedbackResultViewModel feedback = pythonResumeExtractorService.submitFeedback(tokenId, correctedData, rating, retrainOnSubmit);
            model.addAttribute(
                "queueMessage",
                "Feedback saved. Rating: " + feedback.rating() + ", retrained: " + feedback.retrained() + ", dataset entries: " + feedback.totalDatasetEntries()
            );

            FetchDocumentViewModel fetched = pythonResumeExtractorService.fetchDocument(parserId, documentId);
            touchQueueItem(session, documentId, parserId, fetched.getStatus(), fetched.getMessage(), fetched.getFilename());
            upsertResultItem(
                session,
                fetched.getDocumentId(),
                parserId,
                fetched.getFilename(),
                prettyJson(fetched.getParsedData()),
                correctedJson,
                fetched.getTokenId(),
                fetched.getDocumentUrl()
            );
            upsertHistoryItem(
                session,
                fetched.getDocumentId(),
                parserId,
                fetched.getFilename(),
                fetched.getStatus(),
                "feedback_submitted",
                prettyJson(fetched.getParsedData()),
                correctedJson,
                fetched.getTokenId(),
                fetched.getDocumentUrl()
            );
            session.setAttribute(SESSION_EXPANDED_RESULT_ID, fetched.getDocumentId());
        } catch (Exception ex) {
            model.addAttribute("error", ex.getMessage());
        }
        applySharedModel(model, session, parserId, pythonResumeExtractorService.defaultEnvironment());
        return "index";
    }

    @PostMapping("/history/clear")
    public String clearHistory(Model model, HttpSession session) {
        session.removeAttribute(SESSION_HISTORY);
        model.addAttribute("historyMessage", "History cleared.");
        applySharedModel(model, session, pythonResumeExtractorService.defaultParserId(), pythonResumeExtractorService.defaultEnvironment());
        return "history";
    }

    @PostMapping("/queue/kill-all")
    public String killAllQueue(Model model, HttpSession session) {
        try {
            requireLogin(session);
            KillAllResultViewModel result = pythonResumeExtractorService.killAllAndClearQueue();
            session.removeAttribute(SESSION_QUEUE_ITEMS);
            model.addAttribute(
                "queueMessage",
                result.message()
                    + " | cleared_jobs=" + result.clearedJobs()
                    + ", cleared_heartbeats=" + result.clearedHeartbeats()
                    + ", failed_active_documents=" + result.failedActiveDocuments()
            );
        } catch (Exception ex) {
            model.addAttribute("error", ex.getMessage());
        }
        applySharedModel(model, session, pythonResumeExtractorService.defaultParserId(), pythonResumeExtractorService.defaultEnvironment());
        return "index";
    }

    private void requireLogin(HttpSession session) {
        if (session.getAttribute(SESSION_LOGIN_TOKEN) == null) {
            throw new IllegalStateException("Session expired. Please login again.");
        }
    }

    @SuppressWarnings("unchecked")
    private List<HistoryItemViewModel> getHistory(HttpSession session) {
        Object raw = session.getAttribute(SESSION_HISTORY);
        if (raw instanceof List<?> list) {
            return (List<HistoryItemViewModel>) list;
        }
        List<HistoryItemViewModel> rows = new ArrayList<>();
        session.setAttribute(SESSION_HISTORY, rows);
        return rows;
    }

    @SuppressWarnings("unchecked")
    private List<HistoryItemViewModel> getResultItems(HttpSession session) {
        Object raw = session.getAttribute(SESSION_RESULTS);
        if (raw instanceof List<?> list) {
            return (List<HistoryItemViewModel>) list;
        }
        List<HistoryItemViewModel> rows = new ArrayList<>();
        session.setAttribute(SESSION_RESULTS, rows);
        return rows;
    }

    @SuppressWarnings("unchecked")
    private List<QueueSubmissionViewModel> getQueueItems(HttpSession session) {
        Object raw = session.getAttribute(SESSION_QUEUE_ITEMS);
        if (raw instanceof List<?> list) {
            return (List<QueueSubmissionViewModel>) list;
        }
        List<QueueSubmissionViewModel> rows = new ArrayList<>();
        session.setAttribute(SESSION_QUEUE_ITEMS, rows);
        return rows;
    }

    private void upsertQueueItem(HttpSession session, QueueSubmissionViewModel item) {
        List<QueueSubmissionViewModel> queue = getQueueItems(session);
        int foundIdx = -1;
        for (int i = 0; i < queue.size(); i++) {
            if (item.getDocumentId().equals(queue.get(i).getDocumentId())) {
                foundIdx = i;
                break;
            }
        }
        if (foundIdx >= 0) {
            queue.remove(foundIdx);
        }
        queue.add(0, item);
        while (queue.size() > 40) {
            queue.remove(queue.size() - 1);
        }
    }

    private void touchQueueItem(
        HttpSession session,
        String documentId,
        String parserId,
        String status,
        String message,
        String filename
    ) {
        List<QueueSubmissionViewModel> queue = getQueueItems(session);
        QueueSubmissionViewModel current = null;
        for (QueueSubmissionViewModel item : queue) {
            if (documentId.equals(item.getDocumentId())) {
                current = item;
                break;
            }
        }
        QueueSubmissionViewModel updated = new QueueSubmissionViewModel(
            documentId,
            current == null ? "" : current.getJobId(),
            parserId,
            current == null ? pythonResumeExtractorService.defaultEnvironment() : current.getEnvironment(),
            (filename == null || filename.isBlank()) ? (current == null ? "" : current.getFilename()) : filename,
            status,
            message
        );
        upsertQueueItem(session, updated);
    }

    private void removeQueueItem(HttpSession session, String documentId) {
        List<QueueSubmissionViewModel> queue = getQueueItems(session);
        queue.removeIf(item -> documentId.equals(item.getDocumentId()));
    }

    private void upsertResultItem(
        HttpSession session,
        String documentId,
        String parserId,
        String filename,
        String rawJson,
        String feedbackJson,
        String tokenId,
        String documentUrl
    ) {
        List<HistoryItemViewModel> results = getResultItems(session);
        HistoryItemViewModel target = null;
        for (HistoryItemViewModel row : results) {
            if (documentId.equals(row.getDocumentId())) {
                target = row;
                break;
            }
        }
        if (target == null) {
            target = new HistoryItemViewModel();
            target.setDocumentId(documentId);
            target.setParserId(parserId);
            target.setFilename(filename);
            target.setStatus("completed");
            results.add(0, target);
        }
        if (rawJson != null && !rawJson.isBlank()) {
            target.setRawJson(rawJson);
        }
        if (feedbackJson != null && !feedbackJson.isBlank()) {
            target.setFeedbackJson(feedbackJson);
        }
        if (tokenId != null && !tokenId.isBlank()) {
            target.setTokenId(tokenId);
        }
        if (documentUrl != null && !documentUrl.isBlank()) {
            target.setDocumentUrl(documentUrl);
        }
        target.setUpdatedAt(OffsetDateTime.now().toString());
        while (results.size() > 60) {
            results.remove(results.size() - 1);
        }
    }

    private void upsertHistoryItem(
        HttpSession session,
        String documentId,
        String parserId,
        String filename,
        String status,
        String message,
        String rawJson,
        String feedbackJson,
        String tokenId,
        String documentUrl
    ) {
        List<HistoryItemViewModel> history = getHistory(session);
        HistoryItemViewModel target = null;
        for (HistoryItemViewModel row : history) {
            if (documentId.equals(row.getDocumentId())) {
                target = row;
                break;
            }
        }
        if (target == null) {
            target = new HistoryItemViewModel();
            target.setDocumentId(documentId);
            target.setParserId(parserId);
            target.setFilename(filename);
            history.add(0, target);
        }
        target.setStatus(status);
        target.setMessage(message);
        target.setUpdatedAt(OffsetDateTime.now().toString());
        if (rawJson != null && !rawJson.isBlank()) {
            target.setRawJson(rawJson);
        }
        if (feedbackJson != null && !feedbackJson.isBlank()) {
            target.setFeedbackJson(feedbackJson);
        }
        if (tokenId != null && !tokenId.isBlank()) {
            target.setTokenId(tokenId);
        }
        if (documentUrl != null && !documentUrl.isBlank()) {
            target.setDocumentUrl(documentUrl);
        }
        while (history.size() > 40) {
            history.remove(history.size() - 1);
        }
    }

    private void applySharedModel(Model model, HttpSession session, String parserId, String environment) {
        Object user = session.getAttribute(SESSION_LOGIN_USER);
        List<QueueSubmissionViewModel> queueItems = getQueueItems(session);
        model.addAttribute("isLoggedIn", user != null);
        model.addAttribute("loggedInUser", user == null ? "" : String.valueOf(user));
        model.addAttribute("selectedParserId", parserId == null || parserId.isBlank() ? pythonResumeExtractorService.defaultParserId() : parserId);
        model.addAttribute("selectedEnvironment", environment == null || environment.isBlank() ? pythonResumeExtractorService.defaultEnvironment() : environment);
        model.addAttribute("queueItems", queueItems);
        model.addAttribute("latestQueueItem", queueItems.isEmpty() ? null : queueItems.get(0));
        List<HistoryItemViewModel> historyItems = getHistory(session);
        List<HistoryItemViewModel> resultItems = getResultItems(session);
        model.addAttribute("historyItems", historyItems);
        model.addAttribute("resultItems", resultItems);
        model.addAttribute("expandedResultDocumentId", String.valueOf(session.getAttribute(SESSION_EXPANDED_RESULT_ID) == null ? "" : session.getAttribute(SESSION_EXPANDED_RESULT_ID)));
    }

    private String prettyJson(Object value) {
        try {
            return objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(value);
        } catch (JsonProcessingException e) {
            return String.valueOf(value);
        }
    }

    private Map<String, Object> parseJsonMap(String rawJson) {
        try {
            Map<String, Object> parsed = objectMapper.readValue(rawJson, new TypeReference<>() {});
            return parsed == null ? new LinkedHashMap<>() : parsed;
        } catch (Exception ex) {
            throw new IllegalStateException("Invalid corrected JSON: " + ex.getMessage(), ex);
        }
    }
}
