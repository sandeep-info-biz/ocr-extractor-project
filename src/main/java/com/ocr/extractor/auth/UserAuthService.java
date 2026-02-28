package com.ocr.extractor.auth;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.regex.Pattern;

@Service
public class UserAuthService {
    private static final Pattern EMAIL_PATTERN = Pattern.compile("^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+$");
    private final UserAccountRepository userAccountRepository;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    public UserAuthService(UserAccountRepository userAccountRepository) {
        this.userAccountRepository = userAccountRepository;
    }

    public String register(String email, String password) {
        String normalizedEmail = normalizeEmail(email);
        validatePassword(password);
        if (userAccountRepository.existsByEmailIgnoreCase(normalizedEmail)) {
            throw new IllegalStateException("Email already registered.");
        }

        UserAccount user = new UserAccount();
        user.setEmail(normalizedEmail);
        user.setPasswordHash(passwordEncoder.encode(password));
        userAccountRepository.save(user);
        return normalizedEmail;
    }

    public String login(String email, String password) {
        String normalizedEmail = normalizeEmail(email);
        UserAccount user = userAccountRepository.findByEmailIgnoreCase(normalizedEmail)
            .orElseThrow(() -> new IllegalStateException("Invalid email or password."));
        if (!passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new IllegalStateException("Invalid email or password.");
        }
        return user.getEmail();
    }

    private String normalizeEmail(String email) {
        String normalized = String.valueOf(email).trim().toLowerCase();
        if (!StringUtils.hasText(normalized) || !EMAIL_PATTERN.matcher(normalized).matches()) {
            throw new IllegalStateException("Valid email is required.");
        }
        return normalized;
    }

    private void validatePassword(String password) {
        String raw = String.valueOf(password);
        if (raw.length() < 8) {
            throw new IllegalStateException("Password must be at least 8 characters.");
        }
    }
}
