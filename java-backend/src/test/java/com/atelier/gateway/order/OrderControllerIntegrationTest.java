package com.atelier.gateway.order;

import static org.assertj.core.api.Assertions.assertThat;

import com.atelier.gateway.user.UserRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderControllerIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private CacheManager cacheManager;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void cleanDatabase() {
        try {
            jdbcTemplate.update("DELETE FROM order_items");
            jdbcTemplate.update("DELETE FROM orders");
        } catch (BadSqlGrammarException ignored) {
            // The first RED run happens before the order migration exists.
        }
        jdbcTemplate.update("DELETE FROM cart_items");
        userRepository.deleteAll();
        Cache orderLists = cacheManager.getCache("orderLists");
        if (orderLists != null) {
            orderLists.clear();
        }
    }

    @Test
    void createOrderRequiresLogin() {
        webTestClient.post()
            .uri("/api/orders")
            .header("Idempotency-Key", "create-without-login")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void createOrderCopiesSelectedItemsAndIsIdempotent() throws IOException {
        String token = registerAndToken("order@example.com");
        addItem(token, "sku-001", "Vintage Coat", "/media/coat.png", "129.99", 2, true)
            .expectStatus().isOk();
        addItem(token, "sku-002", "Silk Scarf", "/media/scarf.png", "49.00", 1, false)
            .expectStatus().isOk();

        byte[] firstResponse = createOrder(token, "checkout-001")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("PENDING_PAYMENT")
            .jsonPath("$.totalAmount").isEqualTo(259.98)
            .jsonPath("$.items.length()").isEqualTo(1)
            .jsonPath("$.items[0].productId").isEqualTo("sku-001")
            .jsonPath("$.items[0].productName").isEqualTo("Vintage Coat")
            .jsonPath("$.items[0].subtotal").isEqualTo(259.98)
            .returnResult()
            .getResponseBody();
        String orderId = idFrom(firstResponse);

        createOrder(token, "checkout-001")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(orderId);

        webTestClient.get()
            .uri("/api/cart")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items.length()").isEqualTo(1)
            .jsonPath("$.items[0].productId").isEqualTo("sku-002")
            .jsonPath("$.items[0].selected").isEqualTo(false);
    }

    @Test
    void createOrderRejectsMissingIdempotencyKeyAndEmptySelection() {
        String token = registerAndToken("order-errors@example.com");

        webTestClient.post()
            .uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Idempotency key is required");

        createOrder(token, "empty-cart-001")
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.detail").isEqualTo("No selected cart items");
    }

    @Test
    void creatingOrderEvictsTheCurrentUsersCachedOrderList() {
        String email = "cache-create@example.com";
        String token = registerAndToken(email);

        webTestClient.get()
            .uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.orders.length()").isEqualTo(0);

        var userId = userRepository.findByEmailIgnoreCase(email).orElseThrow().getId();
        Cache orderLists = cacheManager.getCache("orderLists");
        assertThat(orderLists).isNotNull();
        assertThat(orderLists.get(userId)).isNotNull();

        addItem(token, "sku-cache", "Cache Coat", "/media/cache.png", "88.00", 1, true)
            .expectStatus().isOk();
        createOrder(token, "cache-create-001")
            .expectStatus().isOk();

        assertThat(orderLists.get(userId)).isNull();

        webTestClient.get()
            .uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.orders.length()").isEqualTo(1);
    }

    @Test
    void usersCanListViewAndCancelOnlyTheirOwnOrders() throws IOException {
        String ownerToken = registerAndToken("order-owner@example.com");
        String otherToken = registerAndToken("order-other@example.com");
        addItem(ownerToken, "sku-003", "Leather Boots", "/media/boots.png", "199.00", 1, true)
            .expectStatus().isOk();
        String orderId = idFrom(createOrder(ownerToken, "owner-order-001")
            .expectStatus().isOk()
            .expectBody()
            .returnResult()
            .getResponseBody());

        webTestClient.get()
            .uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.orders.length()").isEqualTo(1)
            .jsonPath("$.orders[0].id").isEqualTo(orderId)
            .jsonPath("$.orders[0].status").isEqualTo("PENDING_PAYMENT");

        webTestClient.get()
            .uri("/api/orders/{orderId}", orderId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(orderId)
            .jsonPath("$.items.length()").isEqualTo(1);

        webTestClient.get()
            .uri("/api/orders/{orderId}", orderId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + otherToken)
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Order not found");

        webTestClient.post()
            .uri("/api/orders/{orderId}/cancel", orderId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("CANCELLED");

        webTestClient.get()
            .uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.orders[0].status").isEqualTo("CANCELLED");

        webTestClient.post()
            .uri("/api/orders/{orderId}/cancel", orderId)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + ownerToken)
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.detail").isEqualTo("Order cannot be cancelled");
    }

    @Test
    void concurrentRequestsWithSameIdempotencyKeyCreateOnlyOneOrder() throws Exception {
        String token = registerAndToken("order-concurrent@example.com");
        addItem(token, "sku-004", "Cashmere Sweater", "/media/sweater.png", "159.00", 1, true)
            .expectStatus().isOk();

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Callable<byte[]> request = () -> createOrder(token, "concurrent-order-001")
                .expectStatus().isOk()
                .expectBody()
                .returnResult()
                .getResponseBody();
            List<Future<byte[]>> responses = executor.invokeAll(List.of(request, request));

            String firstOrderId = idFrom(responses.get(0).get());
            String secondOrderId = idFrom(responses.get(1).get());
            Integer orderCount = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM orders", Integer.class);

            assertThat(secondOrderId).isEqualTo(firstOrderId);
            assertThat(orderCount).isEqualTo(1);
        } finally {
            executor.shutdownNow();
        }
    }

    private WebTestClient.ResponseSpec createOrder(String token, String idempotencyKey) {
        return webTestClient.post()
            .uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .header("Idempotency-Key", idempotencyKey)
            .exchange();
    }

    private WebTestClient.ResponseSpec addItem(
        String token,
        String productId,
        String productName,
        String productImageUrl,
        String unitPrice,
        int quantity,
        boolean selected
    ) {
        return webTestClient.post()
            .uri("/api/cart/items")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "productId": "%s",
                  "productName": "%s",
                  "productImageUrl": "%s",
                  "unitPrice": %s,
                  "quantity": %d,
                  "selected": %s
                }
                """.formatted(productId, productName, productImageUrl, unitPrice, quantity, selected))
            .exchange();
    }

    private String registerAndToken(String email) {
        byte[] response = webTestClient.post()
            .uri("/api/auth/register")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "email": "%s",
                  "password": "password123",
                  "displayName": "Order User"
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
