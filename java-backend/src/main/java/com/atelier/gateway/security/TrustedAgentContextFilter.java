package com.atelier.gateway.security;

import java.util.UUID;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 2)
public class TrustedAgentContextFilter implements WebFilter {
    public static final String TRUSTED_USER_ID_HEADER = "X-Trusted-User-Id";
    public static final String CONTEXT_TOKEN_HEADER = "X-Agent-Context-Token";
    private final JwtTokenService tokenService;
    private final String internalToken;

    public TrustedAgentContextFilter(
        JwtTokenService tokenService,
        @Value("${agent.internal-token:}") String internalToken
    ) {
        this.tokenService = tokenService;
        this.internalToken = internalToken;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String path = exchange.getRequest().getURI().getPath();
        if (!path.equals("/api/chat") && !path.equals("/api/chat/stream") && !path.startsWith("/api/actions/")) {
            return chain.filter(exchange);
        }
        ServerHttpRequest.Builder request = exchange.getRequest().mutate();
        request.headers(headers -> {
            headers.remove(TRUSTED_USER_ID_HEADER);
            headers.remove(CONTEXT_TOKEN_HEADER);
        });
        String authorization = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        if (authorization != null && authorization.startsWith("Bearer ")) {
            try {
                UUID userId = tokenService.parseUserId(authorization.substring("Bearer ".length()).trim());
                if (!internalToken.isBlank()) {
                    request.header(TRUSTED_USER_ID_HEADER, userId.toString());
                    request.header(CONTEXT_TOKEN_HEADER, internalToken);
                }
            } catch (IllegalArgumentException ignored) {
                // The normal endpoint remains available to anonymous users; no trusted context is forwarded.
            }
        }
        return chain.filter(exchange.mutate().request(request.build()).build());
    }
}
