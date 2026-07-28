package com.atelier.gateway.proxy;

import static org.assertj.core.api.Assertions.assertThat;

import com.atelier.gateway.user.UserRepository;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthRoutePriorityIntegrationTest {
    private static MockWebServer upstream;

    @Autowired
    private WebTestClient webTestClient;

    @Autowired
    private UserRepository userRepository;

    @BeforeAll
    static void startUpstream() throws IOException {
        upstream = new MockWebServer();
        upstream.start();
    }

    @AfterAll
    static void stopUpstream() throws IOException {
        upstream.shutdown();
    }

    @BeforeEach
    void cleanDatabase() {
        userRepository.deleteAll();
    }

    @DynamicPropertySource
    static void gatewayProperties(DynamicPropertyRegistry registry) {
        registry.add("rag.upstream-base-url", () -> upstream.url("/").toString());
    }

    @Test
    void authRegisterIsHandledByJavaInsteadOfPythonProxy() throws Exception {
        webTestClient.post()
            .uri("/api/auth/register")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "email": "route@example.com",
                  "password": "password123",
                  "displayName": "Route User"
                }
                """)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user.email").isEqualTo("route@example.com")
            .jsonPath("$.accessToken").isNotEmpty();

        assertThat(upstream.takeRequest(200, TimeUnit.MILLISECONDS)).isNull();
    }
}
