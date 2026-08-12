package com.atelier.gateway.proxy;

import static org.assertj.core.api.Assertions.assertThat;

import com.atelier.gateway.common.RequestIdWebFilter;
import com.atelier.gateway.security.JwtTokenService;
import com.atelier.gateway.security.TrustedAgentContextFilter;
import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RequestIdWebFilterIntegrationTest {
    private static MockWebServer upstream;

    @Autowired
    private WebTestClient webTestClient;

    @Autowired
    private JwtTokenService tokenService;

    @BeforeAll
    static void startUpstream() throws IOException {
        upstream = new MockWebServer();
        upstream.start();
    }

    @AfterAll
    static void stopUpstream() throws IOException {
        upstream.shutdown();
    }

    @DynamicPropertySource
    static void gatewayProperties(DynamicPropertyRegistry registry) {
        registry.add("rag.upstream-base-url", () -> upstream.url("/").toString());
        registry.add("agent.internal-token", () -> "test-agent-context-token");
    }

    @Test
    void preservesRequestIdOnJavaEndpoints() {
        webTestClient.get()
            .uri("/actuator/health")
            .header(RequestIdWebFilter.REQUEST_ID_HEADER, "java.request-123")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(RequestIdWebFilter.REQUEST_ID_HEADER, "java.request-123");
    }

    @Test
    void replacesInvalidRequestId() {
        webTestClient.get()
            .uri("/actuator/health")
            .header(RequestIdWebFilter.REQUEST_ID_HEADER, "../invalid request")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .value(
                RequestIdWebFilter.REQUEST_ID_HEADER,
                value -> {
                    assertThat(value).hasSize(32);
                    assertThat(value).matches("[0-9a-f]{32}");
                }
            );
    }

    @Test
    void forwardsRequestIdToPythonUpstream() throws Exception {
        upstream.enqueue(
            new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setHeader(RequestIdWebFilter.REQUEST_ID_HEADER, "proxy-request-123")
                .setBody("{\"ok\":true}")
        );

        webTestClient.get()
            .uri("/api/request-id-probe")
            .header(RequestIdWebFilter.REQUEST_ID_HEADER, "proxy-request-123")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(RequestIdWebFilter.REQUEST_ID_HEADER, "proxy-request-123")
            .expectBody()
            .jsonPath("$.ok").isEqualTo(true);

        RecordedRequest request = upstream.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getHeader(RequestIdWebFilter.REQUEST_ID_HEADER))
            .isEqualTo("proxy-request-123");
    }

    @Test
    void forwardsVerifiedSessionOwnerContextToPythonUpstream() throws Exception {
        UUID userId = UUID.randomUUID();
        upstream.enqueue(
            new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("{\"session_id\":\"owned-session\"}")
        );

        webTestClient.post()
            .uri("/api/session")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + tokenService.createAccessToken(userId))
            .header(TrustedAgentContextFilter.TRUSTED_USER_ID_HEADER, "spoofed-user")
            .header(TrustedAgentContextFilter.CONTEXT_TOKEN_HEADER, "spoofed-token")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"session_id\":\"owned-session\"}")
            .exchange()
            .expectStatus().isOk();

        RecordedRequest request = upstream.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getHeader(TrustedAgentContextFilter.TRUSTED_USER_ID_HEADER))
            .isEqualTo(userId.toString());
        assertThat(request.getHeader(TrustedAgentContextFilter.CONTEXT_TOKEN_HEADER))
            .isEqualTo("test-agent-context-token");
    }
}
