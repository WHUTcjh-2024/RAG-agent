package com.atelier.gateway.security;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "auth.jwt")
public record JwtProperties(
    String secret,
    Duration accessTokenTtl
) {
}
