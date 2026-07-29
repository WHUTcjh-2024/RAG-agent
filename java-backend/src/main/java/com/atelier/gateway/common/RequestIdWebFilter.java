package com.atelier.gateway.common;

import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdWebFilter implements WebFilter {
    public static final String REQUEST_ID_HEADER = "X-Request-Id";
    private static final Pattern VALID_REQUEST_ID =
        Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$");
    private static final Logger logger = LoggerFactory.getLogger(RequestIdWebFilter.class);

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String requestId = normalize(
            exchange.getRequest().getHeaders().getFirst(REQUEST_ID_HEADER)
        );
        ServerHttpRequest request = exchange.getRequest()
            .mutate()
            .headers(headers -> headers.set(REQUEST_ID_HEADER, requestId))
            .build();
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders().set(REQUEST_ID_HEADER, requestId);
            return Mono.empty();
        });
        long startedAt = System.nanoTime();
        logger.info(
            "request_received request_id={} method={} path={}",
            requestId,
            request.getMethod(),
            request.getPath().value()
        );
        return chain.filter(exchange.mutate().request(request).build())
            .doFinally(signal -> logger.info(
                "request_completed request_id={} status={} duration_ms={}",
                requestId,
                exchange.getResponse().getStatusCode() == null
                    ? HttpStatus.OK
                    : exchange.getResponse().getStatusCode(),
                (System.nanoTime() - startedAt) / 1_000_000
            ));
    }

    private String normalize(String value) {
        if (value != null) {
            String candidate = value.trim();
            if (VALID_REQUEST_ID.matcher(candidate).matches()) {
                return candidate;
            }
        }
        return UUID.randomUUID().toString().replace("-", "");
    }
}
