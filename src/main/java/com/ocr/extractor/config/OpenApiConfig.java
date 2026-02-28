package com.ocr.extractor.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI ocrExtractorOpenApi() {
        return new OpenAPI()
            .info(
                new Info()
                    .title("OCR Extractor Java API")
                    .version("1.0.0")
                    .description("Swagger for Java-side endpoints.")
                    .contact(new Contact().name("OCR Extractor"))
            );
    }
}
