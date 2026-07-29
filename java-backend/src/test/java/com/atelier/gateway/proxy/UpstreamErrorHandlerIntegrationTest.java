package com.atelier.gateway.proxy;

import com.atelier.gateway.common.RequestIdWebFilter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "rag.upstream-base-url=http://127.0.0.1:1"
)
@AutoConfigureWebTestClient
class UpstreamErrorHandlerIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Test
    void unavailablePythonReturnsTypedErrorWithRequestId() {
        webTestClient.get()
            .uri("/api/upstream-unavailable")
            .header(RequestIdWebFilter.REQUEST_ID_HEADER, "upstream-error-123")
            .exchange()
            .expectStatus().isEqualTo(503)
            .expectHeader()
            .valueEquals(RequestIdWebFilter.REQUEST_ID_HEADER, "upstream-error-123")
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Python upstream is unavailable")
            .jsonPath("$.error.request_id").isEqualTo("upstream-error-123")
            .jsonPath("$.error.code").isEqualTo("UPSTREAM_UNAVAILABLE")
            .jsonPath("$.error.retryable").isEqualTo(true)
            .jsonPath("$.error.stage").isEqualTo("gateway");
    }
}
