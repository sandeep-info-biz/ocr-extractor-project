package com.ocr.extractor.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ocr.extractor.service.PythonResumeExtractorService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

class WebControllerTest {

    @Test
    void constructorRejectsBlankCredentials() {
        PythonResumeExtractorService service = mock(PythonResumeExtractorService.class);
        ObjectMapper objectMapper = new ObjectMapper();

        assertThrows(IllegalStateException.class, () -> new WebController(service, objectMapper, "", "secret"));
        assertThrows(IllegalStateException.class, () -> new WebController(service, objectMapper, "admin", ""));
    }

    @Test
    void constructorAcceptsConfiguredCredentials() {
        PythonResumeExtractorService service = mock(PythonResumeExtractorService.class);
        ObjectMapper objectMapper = new ObjectMapper();

        assertDoesNotThrow(() -> new WebController(service, objectMapper, "ui-user", "strong-password"));
    }
}
