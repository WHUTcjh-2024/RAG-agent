package com.atelier.gateway.decision;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "agent.internal-token=test-internal-token"
)
@AutoConfigureWebTestClient
class DecisionFactsIntegrationTest {
    @Autowired private WebTestClient webTestClient;
    @Autowired private ObjectMapper objectMapper;
    @Autowired private BodyProfileRepository profileRepository;
    @Autowired private ProductSkuFactRepository productFactRepository;

    @BeforeEach
    void cleanDatabase() {
        profileRepository.deleteAll();
        productFactRepository.deleteAll();
    }

    @Test
    void returnsTrustedProfileAndSkuFactsForTheInternalAgent() throws Exception {
        String token = registerAndToken("decision@example.com");
        productFactRepository.saveAndFlush(ProductSkuFact.create(
            "0000000001", "sku-1-m", "M", new BigDecimal("104"),
            new BigDecimal("299"), true, "7 days", "facts-v1"
        ));

        webTestClient.put()
            .uri("/api/profile/body")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"chestCm\":96}")
            .exchange()
            .expectStatus().isOk()
            .expectBody().jsonPath("$.chestCm").isEqualTo(96);

        String userId = userIdFrom(token);
        webTestClient.get()
            .uri(uri -> uri.path("/internal/agent/decision-facts")
                .queryParam("trusted_user_id", userId)
                .queryParam("product_id", "0000000001")
                .build())
            .header("X-Agent-Internal-Token", "test-internal-token")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user_id").isEqualTo(userId)
            .jsonPath("$.profile.chest_cm").isEqualTo(96)
            .jsonPath("$.sku_measurements.size").isEqualTo("M")
            .jsonPath("$.sku_measurements.chest_cm").isEqualTo(104)
            .jsonPath("$.price.amount").isEqualTo(299)
            .jsonPath("$.inventory.in_stock").isEqualTo(true)
            .jsonPath("$.version").isEqualTo("facts-v1");
    }

    @Test
    void rejectsCallsWithoutTheInternalCredential() {
        webTestClient.get()
            .uri(uri -> uri.path("/internal/agent/decision-facts")
                .queryParam("trusted_user_id", "00000000-0000-0000-0000-000000000001")
                .queryParam("product_id", "0000000001")
                .build())
            .exchange()
            .expectStatus().isForbidden();
    }

    private String registerAndToken(String email) throws Exception {
        byte[] body = webTestClient.post()
            .uri("/api/auth/register")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {"email":"%s","password":"password123","displayName":"Decision User"}
                """.formatted(email))
            .exchange()
            .expectStatus().isOk()
            .expectBody().returnResult().getResponseBody();
        return objectMapper.readTree(new String(body, StandardCharsets.UTF_8)).get("accessToken").asText();
    }

    private String userIdFrom(String token) throws Exception {
        byte[] body = webTestClient.get()
            .uri("/api/auth/me")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody().returnResult().getResponseBody();
        JsonNode user = objectMapper.readTree(new String(body, StandardCharsets.UTF_8));
        return user.get("id").asText();
    }
}
