package com.atelier.gateway.health;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HealthControllerIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Test
    void healthReturnsJavaBackendStatus() {
        webTestClient.get()
            .uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok")
            .jsonPath("$.service").isEqualTo("java-backend");
    }
}
