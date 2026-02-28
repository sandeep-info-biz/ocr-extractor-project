package com.ocr.extractor.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.tika.Tika;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class JavaResumeExtractorService {
    private static final Pattern EMAIL_RE = Pattern.compile("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b");
    private static final Pattern PHONE_RE = Pattern.compile("(?:(?:\\+?\\d{1,3}[\\s.-]?)?(?:\\(?\\d{2,4}\\)?[\\s.-]?)?\\d{3,4}[\\s.-]?\\d{3,4})");
    private static final Pattern DOB_RE = Pattern.compile("(?i)(?:date\\s*of\\s*birth|dob)\\s*[:\\-]?\\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})");
    private static final List<String> DEFAULT_SKILLS = List.of(
        "python", "java", "spring boot", "sql", "postgresql", "aws", "docker", "kubernetes", "react", "node.js",
        "machine learning", "nlp", "fastapi", "excel", "power bi", "git", "linux"
    );
    private static final List<String> LANGUAGE_ALLOW = List.of(
        "english", "hindi", "tamil", "telugu", "kannada", "malayalam", "marathi", "gujarati", "bengali", "urdu", "punjabi", "odia"
    );
    private static final List<String> INDIAN_STATES = List.of(
        "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa", "gujarat", "haryana",
        "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur",
        "meghalaya", "mizoram", "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana",
        "tripura", "uttar pradesh", "uttarakhand", "west bengal", "delhi"
    );

    private final Tika tika = new Tika();
    private final ObjectMapper objectMapper;

    public JavaResumeExtractorService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Map<String, Object> extract(MultipartFile resumeFile) {
        try {
            return extract(resumeFile.getBytes(), resumeFile.getOriginalFilename());
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to read uploaded file.", ex);
        }
    }

    public Map<String, Object> extract(byte[] content, String filename) {
        String rawText = extractRawText(content, filename);
        String textLower = rawText.toLowerCase(Locale.ROOT);

        String firstName = "";
        String lastName = "";
        String guessedName = guessName(rawText);
        if (!guessedName.isBlank()) {
            String[] parts = guessedName.split("\\s+");
            firstName = parts[0];
            if (parts.length > 1) {
                lastName = parts[parts.length - 1];
            }
        }

        String email = firstMatch(EMAIL_RE, rawText);
        String phone = normalizePhone(firstMatch(PHONE_RE, rawText));
        String dob = firstGroup(DOB_RE, rawText);
        String nationality = textLower.contains("indian") || textLower.contains("india") ? "India" : "";
        String region = extractRegion(textLower);

        List<String> languages = extractByAllowList(textLower, LANGUAGE_ALLOW);
        List<String> skills = extractByAllowList(textLower, DEFAULT_SKILLS);
        List<String> projects = extractProjects(rawText);

        Map<String, Object> parsed = new LinkedHashMap<>();
        parsed.put("first_name", firstName);
        parsed.put("last_name", lastName);
        parsed.put("phone_number", phone);
        parsed.put("email", email);
        parsed.put("date_of_birth", dob);
        parsed.put("gender", "");
        parsed.put("religion", "");
        parsed.put("marital_status", "");
        parsed.put("nationality_country_name", nationality);
        parsed.put("country_region", region);
        parsed.put("city", "");
        parsed.put("postal_code", extractPostalCode(rawText));
        parsed.put("languages", languages);
        parsed.put("industry_type", "");
        parsed.put("designation_or_position", "");
        parsed.put("total_experience", extractExperienceYears(rawText));
        parsed.put("gulf_expierence", containsGulfExperience(textLower));
        parsed.put("passport_number", extractPassportNumber(rawText));
        parsed.put("passport_expiry_date", "");
        parsed.put("skills", skills);
        parsed.put("projects", projects);
        parsed.put("education", List.of());
        parsed.put("education_degree", "");
        parsed.put("about_description_summary", summarize(rawText));
        parsed.put("linkedin_url", extractLinkedin(rawText));
        parsed.put("raw_text", rawText);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("token_id", UUID.randomUUID().toString());
        out.put("status", "success");
        out.put("generated_at", OffsetDateTime.now().toString());
        out.put("extracted_data", parsed);
        return out;
    }

    public Map<String, Object> loadMappingModelInfo() {
        try {
            Map<String, List<String>> model = objectMapper.readValue(
                new java.io.File("models/resume_mapping_model.json"),
                new TypeReference<>() {}
            );
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("available", true);
            data.put("fields", model.keySet());
            Map<String, Integer> counts = new LinkedHashMap<>();
            for (Map.Entry<String, List<String>> row : model.entrySet()) {
                counts.put(row.getKey(), row.getValue() == null ? 0 : row.getValue().size());
            }
            data.put("counts", counts);
            return data;
        } catch (Exception ex) {
            return Map.of("available", false, "error", ex.getMessage());
        }
    }

    private String extractRawText(MultipartFile file) {
        try {
            return extractRawText(file.getBytes(), file.getOriginalFilename());
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to read uploaded file.", ex);
        }
    }

    private String extractRawText(byte[] content, String filename) {
        try {
            String name = filename == null ? "" : filename.toLowerCase(Locale.ROOT);
            if (name.endsWith(".txt")) {
                return new String(content, StandardCharsets.UTF_8);
            }
            try (InputStream in = new ByteArrayInputStream(content)) {
                return normalizeSpaces(tika.parseToString(in));
            }
        } catch (IOException ex) {
            throw new IllegalStateException("Failed to read uploaded file.", ex);
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to extract text from resume.", ex);
        }
    }

    private String normalizeSpaces(String text) {
        String[] lines = text.replace("\u0000", " ").split("\\R");
        StringBuilder out = new StringBuilder();
        for (String ln : lines) {
            String clean = ln.replaceAll("\\s+", " ").trim();
            if (clean.isBlank()) {
                continue;
            }
            if (out.length() > 0) {
                out.append('\n');
            }
            out.append(clean);
        }
        return out.toString();
    }

    private String firstMatch(Pattern pattern, String text) {
        Matcher m = pattern.matcher(text);
        return m.find() ? m.group() : "";
    }

    private String firstGroup(Pattern pattern, String text) {
        Matcher m = pattern.matcher(text);
        return m.find() ? m.group(1) : "";
    }

    private String normalizePhone(String value) {
        String v = value == null ? "" : value.trim();
        if (v.isBlank()) {
            return "";
        }
        String digits = v.replaceAll("\\D", "");
        if (digits.length() < 10) {
            return "";
        }
        return value;
    }

    private String guessName(String text) {
        String[] lines = text.split("\\R");
        int limit = Math.min(lines.length, 8);
        for (int i = 0; i < limit; i++) {
            String line = lines[i].trim();
            if (line.isBlank()) {
                continue;
            }
            if (line.length() > 60) {
                continue;
            }
            if (line.contains("@") || line.matches(".*\\d.*")) {
                continue;
            }
            String[] parts = line.split("\\s+");
            if (parts.length < 2 || parts.length > 4) {
                continue;
            }
            return line;
        }
        return "";
    }

    private String extractPostalCode(String text) {
        Matcher m = Pattern.compile("\\b\\d{6}\\b").matcher(text);
        return m.find() ? m.group() : "";
    }

    private Integer extractExperienceYears(String text) {
        Matcher m = Pattern.compile("(\\d{1,2})\\s*\\+?\\s*(?:years?|yrs?)", Pattern.CASE_INSENSITIVE).matcher(text);
        int max = -1;
        while (m.find()) {
            max = Math.max(max, Integer.parseInt(m.group(1)));
        }
        return max >= 0 ? max : null;
    }

    private boolean containsGulfExperience(String textLower) {
        return textLower.matches(".*\\b(gulf|uae|dubai|qatar|oman|kuwait|bahrain|saudi)\\b.*");
    }

    private String extractPassportNumber(String text) {
        Matcher m = Pattern.compile("\\b[A-Z][0-9]{7}\\b").matcher(text.toUpperCase(Locale.ROOT));
        return m.find() ? m.group() : "";
    }

    private String summarize(String text) {
        String[] lines = text.split("\\R");
        List<String> out = new ArrayList<>();
        for (String ln : lines) {
            String clean = ln.trim();
            if (clean.isBlank()) {
                continue;
            }
            if (clean.contains("@") || clean.matches(".*\\+?\\d[\\d\\s\\-().]{8,}.*")) {
                continue;
            }
            out.add(clean);
            if (String.join(" ", out).length() > 260 || out.size() >= 4) {
                break;
            }
        }
        return String.join(" ", out);
    }

    private String extractLinkedin(String text) {
        Matcher m = Pattern.compile("\\b(?:https?://)?(?:www\\.)?linkedin\\.com/\\S+\\b", Pattern.CASE_INSENSITIVE).matcher(text);
        return m.find() ? m.group() : "";
    }

    private List<String> extractByAllowList(String textLower, List<String> allowList) {
        Set<String> out = new LinkedHashSet<>();
        for (String item : allowList) {
            String pattern = "\\b" + Pattern.quote(item.toLowerCase(Locale.ROOT)) + "\\b";
            if (textLower.matches("(?s).*" + pattern + ".*")) {
                out.add(toTitle(item));
            }
        }
        return new ArrayList<>(out);
    }

    private String toTitle(String value) {
        if (value.contains(".")) {
            return value;
        }
        String[] parts = value.split("\\s+");
        StringBuilder out = new StringBuilder();
        for (String part : parts) {
            if (part.isBlank()) {
                continue;
            }
            if (out.length() > 0) {
                out.append(' ');
            }
            out.append(part.substring(0, 1).toUpperCase(Locale.ROOT));
            out.append(part.substring(1).toLowerCase(Locale.ROOT));
        }
        return out.toString();
    }

    private String extractRegion(String textLower) {
        for (String state : INDIAN_STATES) {
            String pattern = "\\b" + Pattern.quote(state) + "\\b";
            if (textLower.matches("(?s).*" + pattern + ".*")) {
                return toTitle(state);
            }
        }
        Matcher m = Pattern.compile("(?i)\\bstate\\b\\s*[:\\-]?\\s*([A-Za-z ]{3,40})").matcher(textLower);
        if (m.find()) {
            return toTitle(m.group(1).trim());
        }
        return "";
    }

    private List<String> extractProjects(String text) {
        String[] lines = text.split("\\R");
        List<String> projects = new ArrayList<>();
        boolean inProjects = false;
        for (String raw : lines) {
            String line = raw.trim();
            if (line.isBlank()) {
                continue;
            }
            String lower = line.toLowerCase(Locale.ROOT);
            if (lower.matches("^(projects?|personal projects?|professional projects?)\\s*:?$")) {
                inProjects = true;
                continue;
            }
            if (inProjects && lower.matches("^(skills?|education|experience|summary|certifications?)\\s*:?.*$")) {
                break;
            }
            if (inProjects) {
                String clean = line.replaceFirst("^[\\-•*\\d.()\\s]+", "").trim();
                if (!clean.isBlank() && clean.split("\\s+").length >= 2) {
                    projects.add(clean);
                }
                if (projects.size() >= 8) {
                    break;
                }
            }
        }
        return projects;
    }
}
