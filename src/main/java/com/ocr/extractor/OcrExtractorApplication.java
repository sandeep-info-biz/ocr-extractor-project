package com.ocr.extractor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OcrExtractorApplication {
    public static void main(String[] args) {
        SpringApplication.run(OcrExtractorApplication.class, args);
    }
}
