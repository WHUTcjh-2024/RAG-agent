package com.atelier.gateway.cart;

import com.atelier.gateway.common.ApiException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class AgentActionTokenService {
    private final String secret;
    private final ObjectMapper objectMapper;

    public AgentActionTokenService(
        @Value("${agent.internal-token:}") String secret,
        ObjectMapper objectMapper
    ) {
        this.secret = secret;
        this.objectMapper = objectMapper;
    }

    public AgentCartAction verify(String token) {
        if (secret.isBlank() || token == null || token.isBlank()) {
            throw invalidToken();
        }
        String[] parts = token.split("\\.", -1);
        if (parts.length != 2 || !constantTimeEquals(sign(parts[0]), parts[1])) {
            throw invalidToken();
        }
        try {
            AgentCartAction action = objectMapper.readValue(decode(parts[0]), AgentCartAction.class);
            if (action.exp() <= Instant.now().getEpochSecond()) throw invalidToken();
            return action;
        } catch (Exception ex) {
            throw invalidToken();
        }
    }

    private String sign(String payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(payload.getBytes(StandardCharsets.US_ASCII)));
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot validate agent action token", ex);
        }
    }

    private byte[] decode(String value) {
        return Base64.getUrlDecoder().decode(value);
    }

    private boolean constantTimeEquals(String left, String right) {
        return java.security.MessageDigest.isEqual(
            left.getBytes(StandardCharsets.US_ASCII), right.getBytes(StandardCharsets.US_ASCII)
        );
    }

    private ApiException invalidToken() {
        return new ApiException(HttpStatus.CONFLICT, "Agent confirmation is invalid or expired");
    }

    public record AgentCartAction(
        String action_id, String task_id, String user_id, String product_id,
        String product_name, String product_image_url, String expected_price,
        Integer quantity, long exp
    ) { }
}
