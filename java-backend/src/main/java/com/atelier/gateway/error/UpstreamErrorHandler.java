package com.atelier.gateway.error;

import java.nio.charset.StandardCharsets;
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
    private static final byte[] UPSTREAM_UNAVAILABLE =
        "{\"detail\":\"Python upstream is unavailable\"}".getBytes(StandardCharsets.UTF_8);

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        if (exchange.getResponse().isCommitted() || !isProxiedPath(exchange)) {
            return Mono.error(ex);
        }
        exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        DataBuffer body = exchange.getResponse().bufferFactory().wrap(UPSTREAM_UNAVAILABLE);
        return exchange.getResponse().writeWith(Mono.just(body));
    }

    private boolean isProxiedPath(ServerWebExchange exchange) {
        String path = exchange.getRequest().getPath().pathWithinApplication().value();
        if (path.startsWith("/api/auth/")) {
            return false;
        }
        return path.startsWith("/api/") || path.startsWith("/media/");
    }
}
