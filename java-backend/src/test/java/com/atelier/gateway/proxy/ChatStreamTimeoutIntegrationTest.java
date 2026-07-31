package com.atelier.gateway.proxy;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient(timeout = "5s")
class ChatStreamTimeoutIntegrationTest {
    private static MockWebServer upstream;

    @Autowired
    private WebTestClient webTestClient;

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
        registry.add(
            "spring.cloud.gateway.httpclient.response-timeout",
            () -> Duration.ofMillis(50)
        );
    }

    @Test
    void chatStreamRouteIsNotCutOffByNormalGatewayTimeout() {
        String body = """
            event: status
            data: {"state":"processing"}

            event: done
            data: {"ok":true}

            """;
        upstream.enqueue(
            new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", MediaType.TEXT_EVENT_STREAM_VALUE)
                .setHeadersDelay(150, TimeUnit.MILLISECONDS)
                .setChunkedBody(body, 16)
                .throttleBody(16, 100, TimeUnit.MILLISECONDS)
        );

        webTestClient.post()
            .uri("/api/chat/stream")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .bodyValue("message=test&session_id=java-stream")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .expectBody(String.class)
            .value(response -> {
                assertThat(response).contains("event: status");
                assertThat(response).contains("event: done");
            });
    }
}
