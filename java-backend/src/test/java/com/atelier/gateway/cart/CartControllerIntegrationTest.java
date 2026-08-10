package com.atelier.gateway.cart;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.reset;

import com.atelier.gateway.catalog.CatalogProductGateway;
import com.atelier.gateway.catalog.CatalogProductSnapshot;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.user.UserRepository;
import com.atelier.gateway.security.JwtTokenService;
import com.atelier.gateway.wardrobe.WardrobeFeedbackEventRepository;
import com.atelier.gateway.wardrobe.WardrobeItemRepository;
import com.atelier.gateway.wardrobe.WardrobeVersionRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Base64;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "agent.internal-token=agent-action-test-secret"
)
@AutoConfigureWebTestClient
class CartControllerIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Autowired
    private UserRepository userRepository;

    @MockBean
    private CatalogProductGateway catalogProductGateway;

    @Autowired
    private AgentCartActionCommitRepository actionCommitRepository;

    @Autowired
    private WardrobeItemRepository wardrobeItemRepository;

    @Autowired
    private WardrobeFeedbackEventRepository wardrobeFeedbackRepository;

    @Autowired
    private WardrobeVersionRepository wardrobeVersionRepository;

    @Autowired
    private JwtTokenService jwtTokenService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void cleanDatabase() {
        actionCommitRepository.deleteAll();
        wardrobeFeedbackRepository.deleteAll();
        wardrobeItemRepository.deleteAll();
        wardrobeVersionRepository.deleteAll();
        reset(catalogProductGateway);
        try {
            jdbcTemplate.update("DELETE FROM cart_items");
        } catch (BadSqlGrammarException ignored) {
            // The first RED run happens before the cart migration exists.
        }
        userRepository.deleteAll();
    }

    @Test
    void addItemRequiresLogin() {
        webTestClient.post()
            .uri("/api/cart/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(addItemJson("sku-001", 1))
            .exchange()
            .expectStatus().isEqualTo(401)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Login required");
    }

    @Test
    void addItemUsesServerCatalogSnapshot() throws IOException {
        String token = registerAndToken("cart@example.com");
        stubCatalog("sku-001", "Vintage Coat", "/media/coat.png", "129.99");

        byte[] response = webTestClient.post()
            .uri("/api/cart/items")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "productId": "sku-001",
                  "productName": "Forged Coat",
                  "productImageUrl": "/media/forged.png",
                  "unitPrice": 0.01,
                  "quantity": 2
                }
                """)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isNotEmpty()
            .jsonPath("$.productId").isEqualTo("sku-001")
            .jsonPath("$.productName").isEqualTo("Vintage Coat")
            .jsonPath("$.productImageUrl").isEqualTo("/media/coat.png")
            .jsonPath("$.unitPrice").isEqualTo(129.99)
            .jsonPath("$.quantity").isEqualTo(2)
            .jsonPath("$.selected").isEqualTo(true)
            .returnResult()
            .getResponseBody();
        String itemId = objectMapper.readTree(new String(response, StandardCharsets.UTF_8)).get("id").asText();

        webTestClient.get()
            .uri("/api/cart")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items.length()").isEqualTo(1)
            .jsonPath("$.items[0].id").isEqualTo(itemId)
            .jsonPath("$.items[0].productId").isEqualTo("sku-001")
            .jsonPath("$.items[0].quantity").isEqualTo(2);
    }

    @Test
    void addItemRejectsMissingOrUnavailableCatalogProducts() {
        String token = registerAndToken("unavailable@example.com");

        given(catalogProductGateway.fetch("missing-sku"))
            .willThrow(new ApiException(HttpStatus.NOT_FOUND, "商品不存在"));
        addItemRequest(token, "missing-sku", 1)
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.detail").isEqualTo("商品不存在");

        given(catalogProductGateway.fetch("unavailable-sku"))
            .willThrow(new ApiException(HttpStatus.BAD_GATEWAY, "商品目录暂不可用"));
        addItemRequest(token, "unavailable-sku", 1)
            .expectStatus().isEqualTo(502)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("商品目录暂不可用");
    }

    @Test
    void repeatedAddForSameProductIncrementsQuantityAndRefreshesSnapshot() {
        String token = registerAndToken("repeat@example.com");

        addItem(token, "sku-001", "Old Coat", "/media/old.png", "129.99", 2)
            .expectStatus().isOk();

        addItem(token, "sku-001", "Updated Coat", "/media/new.png", "139.50", 3)
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.productId").isEqualTo("sku-001")
            .jsonPath("$.productName").isEqualTo("Updated Coat")
            .jsonPath("$.productImageUrl").isEqualTo("/media/new.png")
            .jsonPath("$.unitPrice").isEqualTo(139.50)
            .jsonPath("$.quantity").isEqualTo(5);

        webTestClient.get()
            .uri("/api/cart")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items.length()").isEqualTo(1)
            .jsonPath("$.items[0].quantity").isEqualTo(5);
    }

    @Test
    void agentConfirmationVerifiesFactsAndIsIdempotent() throws Exception {
        String token = registerAndToken("agent-action@example.com");
        UUID userId = jwtTokenService.parseUserId(token);
        stubCatalog("agent-sku", "Agent Coat", "/media/coat.png", "129.99");
        String confirmation = agentConfirmationToken("action-1", userId, "agent-sku", "129.99");

        byte[] first = webTestClient.post()
            .uri("/api/cart/agent-actions/confirm")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"confirmationToken\":\"%s\"}".formatted(confirmation))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.productId").isEqualTo("agent-sku")
            .jsonPath("$.unitPrice").isEqualTo(129.99)
            .jsonPath("$.quantity").isEqualTo(1)
            .returnResult().getResponseBody();

        webTestClient.post()
            .uri("/api/cart/agent-actions/confirm")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"confirmationToken\":\"%s\"}".formatted(confirmation))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(idFrom(first))
            .jsonPath("$.quantity").isEqualTo(1);

        webTestClient.delete()
            .uri("/api/cart/items/{itemId}", idFrom(first))
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isNoContent();

        webTestClient.post()
            .uri("/api/cart/agent-actions/confirm")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"confirmationToken\":\"%s\"}".formatted(confirmation))
            .exchange()
            .expectStatus().isEqualTo(409);
    }

    @Test
    void agentConfirmationRejectsAStaleServerPrice() throws Exception {
        String token = registerAndToken("stale-agent-price@example.com");
        UUID userId = jwtTokenService.parseUserId(token);
        stubCatalog("agent-stale-sku", "Updated Coat", "/media/updated.png", "139.99");
        String confirmation = agentConfirmationToken("action-stale", userId, "agent-stale-sku", "129.99");

        webTestClient.post()
            .uri("/api/cart/agent-actions/confirm")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"confirmationToken\":\"%s\"}".formatted(confirmation))
            .exchange()
            .expectStatus().isEqualTo(409)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Product price changed; request a new confirmation");
    }

    @Test
    void wardrobeIsVersionedAndScopedToTheCurrentUser() throws IOException {
        String ownerToken = registerAndToken("wardrobe-owner@example.com");
        String otherToken = registerAndToken("wardrobe-other@example.com");
        byte[] response = webTestClient.post()
            .uri("/api/wardrobe/items")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {"name":"White shirt","category":"Shirt","color":"White","sourceProductId":"sku-wardrobe"}
                """)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.version").isEqualTo(1)
            .jsonPath("$.items.length()").isEqualTo(1)
            .jsonPath("$.items[0].name").isEqualTo("White shirt")
            .returnResult().getResponseBody();
        String itemId = objectMapper.readTree(new String(response, StandardCharsets.UTF_8))
            .at("/items/0/id").asText();

        webTestClient.delete()
            .uri("/api/wardrobe/items/{itemId}", itemId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + otherToken)
            .exchange()
            .expectStatus().isNotFound();

        webTestClient.post()
            .uri("/api/wardrobe/feedback")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"taskId\":\"wardrobe-task\",\"planRef\":\"plan-1\",\"itemRef\":\"%s\",\"outcome\":\"ADOPTED\",\"fitFeedback\":\"GOOD_FIT\"}".formatted(itemId))
            .exchange()
            .expectStatus().isNoContent();

        webTestClient.delete()
            .uri("/api/wardrobe/items/{itemId}", itemId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .exchange()
            .expectStatus().isNoContent();

        webTestClient.get()
            .uri("/api/wardrobe")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.version").isEqualTo(2)
            .jsonPath("$.items.length()").isEqualTo(0);
    }

    @Test
    void updateItemChangesQuantityAndSelectedFlag() throws IOException {
        String token = registerAndToken("update@example.com");
        String itemId = idFrom(addItem(token, "sku-002", "Silk Scarf", "/media/scarf.png", "49.00", 1)
            .expectStatus().isOk()
            .expectBody()
            .returnResult()
            .getResponseBody());

        webTestClient.patch()
            .uri("/api/cart/items/{itemId}", itemId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "quantity": 4,
                  "selected": false
                }
                """)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(itemId)
            .jsonPath("$.quantity").isEqualTo(4)
            .jsonPath("$.selected").isEqualTo(false);
    }

    @Test
    void updateRejectsInvalidQuantity() throws IOException {
        String token = registerAndToken("invalid@example.com");
        String itemId = idFrom(addItem(token, "sku-003", "Leather Belt", "/media/belt.png", "59.00", 1)
            .expectStatus().isOk()
            .expectBody()
            .returnResult()
            .getResponseBody());

        webTestClient.patch()
            .uri("/api/cart/items/{itemId}", itemId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "quantity": 0
                }
                """)
            .exchange()
            .expectStatus().isEqualTo(400)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Quantity must be at least 1");
    }

    @Test
    void deleteItemRemovesOnlyThatItem() throws IOException {
        String token = registerAndToken("delete@example.com");
        String firstId = idFrom(addItem(token, "sku-004", "Boots", "/media/boots.png", "199.00", 1)
            .expectStatus().isOk()
            .expectBody()
            .returnResult()
            .getResponseBody());
        addItem(token, "sku-005", "Bag", "/media/bag.png", "89.00", 1)
            .expectStatus().isOk();

        webTestClient.delete()
            .uri("/api/cart/items/{itemId}", firstId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isNoContent();

        webTestClient.get()
            .uri("/api/cart")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items.length()").isEqualTo(1)
            .jsonPath("$.items[0].productId").isEqualTo("sku-005");
    }

    @Test
    void clearCartRemovesCurrentUserItems() {
        String token = registerAndToken("clear@example.com");
        addItem(token, "sku-006", "Hat", "/media/hat.png", "39.00", 1)
            .expectStatus().isOk();
        addItem(token, "sku-007", "Gloves", "/media/gloves.png", "29.00", 1)
            .expectStatus().isOk();

        webTestClient.delete()
            .uri("/api/cart")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isNoContent();

        webTestClient.get()
            .uri("/api/cart")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items.length()").isEqualTo(0);
    }

    @Test
    void usersCannotSeeOrModifyEachOthersItems() throws IOException {
        String ownerToken = registerAndToken("owner@example.com");
        String otherToken = registerAndToken("other@example.com");
        String ownerItemId = idFrom(addItem(ownerToken, "sku-008", "Watch", "/media/watch.png", "249.00", 1)
            .expectStatus().isOk()
            .expectBody()
            .returnResult()
            .getResponseBody());

        webTestClient.get()
            .uri("/api/cart")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + otherToken)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items.length()").isEqualTo(0);

        webTestClient.delete()
            .uri("/api/cart/items/{itemId}", ownerItemId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + otherToken)
            .exchange()
            .expectStatus().isEqualTo(404)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Cart item not found");
    }

    private WebTestClient.ResponseSpec addItem(
        String token,
        String productId,
        String productName,
        String productImageUrl,
        String unitPrice,
        int quantity
    ) {
        stubCatalog(productId, productName, productImageUrl, unitPrice);
        return addItemRequest(token, productId, quantity);
    }

    private WebTestClient.ResponseSpec addItemRequest(String token, String productId, int quantity) {
        return webTestClient.post()
            .uri("/api/cart/items")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(addItemJson(productId, quantity))
            .exchange();
    }

    private void stubCatalog(String productId, String productName, String productImageUrl, String unitPrice) {
        given(catalogProductGateway.fetch(productId)).willReturn(new CatalogProductSnapshot(
            productId, productName, productImageUrl, new BigDecimal(unitPrice)
        ));
    }

    private String addItemJson(String productId, int quantity) {
        return """
            {
              "productId": "%s",
              "quantity": %d
            }
            """.formatted(productId, quantity);
    }

    private String registerAndToken(String email) {
        byte[] response = webTestClient.post()
            .uri("/api/auth/register")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "email": "%s",
                  "password": "password123",
                  "displayName": "Cart User"
                }
                """.formatted(email))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .returnResult()
            .getResponseBody();
        return accessTokenFrom(response);
    }

    private String idFrom(byte[] response) throws IOException {
        JsonNode json = objectMapper.readTree(new String(response, StandardCharsets.UTF_8));
        return json.get("id").asText();
    }

    private String accessTokenFrom(byte[] response) {
        try {
            JsonNode json = objectMapper.readTree(new String(response, StandardCharsets.UTF_8));
            return json.get("accessToken").asText();
        } catch (IOException ex) {
            throw new IllegalStateException("Could not parse auth response", ex);
        }
    }

    private String agentConfirmationToken(String actionId, UUID userId, String productId, String price) throws Exception {
        String payload = """
            {"action_id":"%s","task_id":"task-1","user_id":"%s","product_id":"%s","product_name":"Agent Coat","product_image_url":"/media/coat.png","expected_price":"%s","quantity":1,"exp":%d}
            """.formatted(actionId, userId, productId, price, Instant.now().plusSeconds(600).getEpochSecond());
        String encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(payload.getBytes(StandardCharsets.UTF_8));
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec("agent-action-test-secret".getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String signature = Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(encoded.getBytes(StandardCharsets.US_ASCII)));
        return encoded + "." + signature;
    }
}
