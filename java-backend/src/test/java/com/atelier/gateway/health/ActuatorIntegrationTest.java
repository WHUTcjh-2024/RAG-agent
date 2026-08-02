package com.atelier.gateway.health;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ActuatorIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Test
    void exposesPrometheusButNotEnvironmentValues() {
        webTestClient.get()
            .uri("/actuator/prometheus")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .value(body -> assertThat(body).contains("jvm_info"));

        webTestClient.get()
            .uri("/actuator/env")
            .exchange()
            .expectStatus().isNotFound();
    }
}
