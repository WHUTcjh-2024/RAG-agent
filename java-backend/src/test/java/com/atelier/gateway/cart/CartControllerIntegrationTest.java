package com.atelier.gateway.cart;

import static org.assertj.core.api.Assertions.assertThat;

import com.atelier.gateway.user.UserRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CartControllerIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void cleanDatabase() {
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
            .bodyValue(addItemJson("sku-001", "Vintage Coat", "/media/coat.png", "129.99", 1))
            .exchange()
            .expectStatus().isEqualTo(401)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Login required");
    }

    @Test
    void addItemReturnsSnapshotAndCartListsCurrentUserItems() throws IOException {
        String token = registerAndToken("cart@example.com");

        byte[] response = addItem(token, "sku-001", "Vintage Coat", "/media/coat.png", "129.99", 2)
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
        return webTestClient.post()
            .uri("/api/cart/items")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(addItemJson(productId, productName, productImageUrl, unitPrice, quantity))
            .exchange();
    }

    private String addItemJson(String productId, String productName, String productImageUrl, String unitPrice, int quantity) {
        return """
            {
              "productId": "%s",
              "productName": "%s",
              "productImageUrl": "%s",
              "unitPrice": %s,
              "quantity": %d
            }
            """.formatted(productId, productName, productImageUrl, unitPrice, quantity);
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
}
