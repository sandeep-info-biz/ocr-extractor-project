package com.ocr.extractor.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ocr.extractor.auth.UserAuthService;
import com.ocr.extractor.service.JavaWorkflowService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.Mockito.mock;

class WebControllerTest {

    @Test
    void constructorAcceptsDependencies() {
        JavaWorkflowService service = mock(JavaWorkflowService.class);
        ObjectMapper objectMapper = new ObjectMapper();
        UserAuthService userAuthService = mock(UserAuthService.class);

        assertDoesNotThrow(() -> new WebController(service, objectMapper, userAuthService));
    }
}
