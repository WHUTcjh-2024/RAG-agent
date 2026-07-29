package com.atelier.gateway.error;

import com.atelier.gateway.common.RequestIdWebFilter;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Objects;
import org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class UpstreamErrorHandler implements ErrorWebExceptionHandler {
    private final ObjectMapper objectMapper;

    public UpstreamErrorHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        if (exchange.getResponse().isCommitted() || !isProxiedPath(exchange)) {
            return Mono.error(ex);
        }
        exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        DataBuffer body = exchange.getResponse().bufferFactory().wrap(
            upstreamUnavailableBody(exchange)
        );
        return exchange.getResponse().writeWith(Mono.just(body));
    }

    private byte[] upstreamUnavailableBody(ServerWebExchange exchange) {
        String requestId = Objects.requireNonNullElse(
            exchange.getRequest().getHeaders().getFirst(RequestIdWebFilter.REQUEST_ID_HEADER),
            "unknown"
        );
        Map<String, Object> error = Map.of(
            "request_id", requestId,
            "code", "UPSTREAM_UNAVAILABLE",
            "message", "Python upstream is unavailable",
            "retryable", true,
            "stage", "gateway",
            "details", Map.of()
        );
        try {
            return objectMapper.writeValueAsBytes(
                Map.of("detail", "Python upstream is unavailable", "error", error)
            );
        } catch (JsonProcessingException serializationError) {
            return "{\"detail\":\"Python upstream is unavailable\"}"
                .getBytes(StandardCharsets.UTF_8);
        }
    }

    private boolean isProxiedPath(ServerWebExchange exchange) {
        String path = exchange.getRequest().getPath().pathWithinApplication().value();
        if (path.startsWith("/api/auth/")) {
            return false;
        }
        return path.startsWith("/api/") || path.startsWith("/media/");
    }
}
