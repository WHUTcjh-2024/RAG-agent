package com.atelier.gateway.auth;

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
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthControllerIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Autowired
    private UserRepository userRepository;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void cleanDatabase() {
        userRepository.deleteAll();
    }

    @Test
    void registerCreatesUserAndReturnsAccessToken() {
        register("USER@example.com", "password123", "陈昊")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accessToken").isNotEmpty()
            .jsonPath("$.user.email").isEqualTo("user@example.com")
            .jsonPath("$.user.displayName").isEqualTo("陈昊")
            .jsonPath("$.user.provider").isEqualTo("LOCAL");

        assertThat(userRepository.findByEmailIgnoreCase("user@example.com"))
            .hasValueSatisfying(user -> assertThat(user.getPasswordHash()).isNotEqualTo("password123"));
    }

    @Test
    void duplicateEmailRegistrationFails() {
        register("user@example.com", "password123", "陈昊")
            .expectStatus().isOk();

        register("USER@example.com", "password123", "另一个用户")
            .expectStatus().isEqualTo(409)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("邮箱已经被注册");
    }

    @Test
    void shortPasswordRegistrationFails() {
        register("short@example.com", "1234567", "陈昊")
            .expectStatus().isEqualTo(400)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("密码长度至少 8 位");
    }

    @Test
    void loginReturnsAccessToken() {
        register("login@example.com", "password123", "陈昊")
            .expectStatus().isOk();

        webTestClient.post()
            .uri("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "email": "LOGIN@example.com",
                  "password": "password123"
                }
                """)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accessToken").isNotEmpty()
            .jsonPath("$.user.email").isEqualTo("login@example.com")
            .jsonPath("$.user.displayName").isEqualTo("陈昊");
    }

    @Test
    void wrongPasswordLoginFailsWithoutRevealingWhichFieldWasWrong() {
        register("login@example.com", "password123", "陈昊")
            .expectStatus().isOk();

        webTestClient.post()
            .uri("/api/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "email": "login@example.com",
                  "password": "wrong-password"
                }
                """)
            .exchange()
            .expectStatus().isEqualTo(401)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("邮箱或密码错误");
    }

    @Test
    void meReturnsCurrentUserForValidToken() throws IOException {
        byte[] response = register("me@example.com", "password123", "陈昊")
            .expectStatus().isOk()
            .expectBody()
            .returnResult()
            .getResponseBody();
        String token = accessTokenFrom(response);

        webTestClient.get()
            .uri("/api/auth/me")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.email").isEqualTo("me@example.com")
            .jsonPath("$.displayName").isEqualTo("陈昊")
            .jsonPath("$.provider").isEqualTo("LOCAL");
    }

    @Test
    void meWithoutTokenReturnsUnauthorized() {
        webTestClient.get()
            .uri("/api/auth/me")
            .exchange()
            .expectStatus().isEqualTo(401)
            .expectBody()
            .jsonPath("$.detail").isEqualTo("请先登录");
    }

    private WebTestClient.ResponseSpec register(String email, String password, String displayName) {
        return webTestClient.post()
            .uri("/api/auth/register")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "email": "%s",
                  "password": "%s",
                  "displayName": "%s"
                }
                """.formatted(email, password, displayName))
            .exchange();
    }

    private String accessTokenFrom(byte[] response) throws IOException {
        JsonNode json = objectMapper.readTree(new String(response, StandardCharsets.UTF_8));
        return json.get("accessToken").asText();
    }
}
