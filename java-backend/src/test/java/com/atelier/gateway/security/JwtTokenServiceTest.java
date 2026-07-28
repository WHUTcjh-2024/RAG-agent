package com.atelier.gateway.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class JwtTokenServiceTest {
    @Test
    void createsAndParsesAccessToken() {
        JwtProperties properties = new JwtProperties(
            "atelier-local-dev-secret-at-least-32-bytes",
            Duration.ofHours(2)
        );
        JwtTokenService tokenService = new JwtTokenService(properties);
        UUID userId = UUID.randomUUID();

        String token = tokenService.createAccessToken(userId);

        assertThat(token).isNotBlank();
        assertThat(tokenService.parseUserId(token)).isEqualTo(userId);
    }

    @Test
    void rejectsInvalidToken() {
        JwtProperties properties = new JwtProperties(
            "atelier-local-dev-secret-at-least-32-bytes",
            Duration.ofHours(2)
        );
        JwtTokenService tokenService = new JwtTokenService(properties);

        assertThatThrownBy(() -> tokenService.parseUserId("not-a-token"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("Invalid access token");
    }
}
