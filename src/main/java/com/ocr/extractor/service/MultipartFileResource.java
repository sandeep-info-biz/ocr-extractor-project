package com.ocr.extractor.service;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

public final class MultipartFileResource extends ByteArrayResource {
    private final String filename;

    public MultipartFileResource(MultipartFile file) throws IOException {
        super(file.getBytes());
        this.filename = file.getOriginalFilename();
    }

    @Override
    public String getFilename() {
        return filename;
    }
}
