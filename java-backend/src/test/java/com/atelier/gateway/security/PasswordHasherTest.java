package com.atelier.gateway.security;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class PasswordHasherTest {
    private final PasswordHasher passwordHasher = new PasswordHasher();

    @Test
    void hashesPasswordWithoutKeepingPlainText() {
        String hash = passwordHasher.hash("password123");

        assertThat(hash).isNotEqualTo("password123");
        assertThat(hash).startsWith("$2");
        assertThat(passwordHasher.matches("password123", hash)).isTrue();
        assertThat(passwordHasher.matches("wrong-password", hash)).isFalse();
    }
}
