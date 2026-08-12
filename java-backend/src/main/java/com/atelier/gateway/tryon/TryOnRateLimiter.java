package com.atelier.gateway.tryon;

import java.util.List;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import com.atelier.gateway.common.ApiException;

@Component
public class TryOnRateLimiter {
    private static final DefaultRedisScript<Long> INCREMENT_WITH_WINDOW = new DefaultRedisScript<>("""
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
        return count
        """, Long.class);

    private final StringRedisTemplate redisTemplate;
    private final TryOnProperties properties;

    public TryOnRateLimiter(StringRedisTemplate redisTemplate, TryOnProperties properties) {
        this.redisTemplate = redisTemplate;
        this.properties = properties;
    }

    public void check(UUID userId) {
        Long count = redisTemplate.execute(
            INCREMENT_WITH_WINDOW,
            List.of("fitme:tryon:rate:" + userId),
            Long.toString(properties.rateLimitWindow().toMillis())
        );
        if (count == null || count > properties.rateLimitCount()) {
            throw new ApiException(HttpStatus.TOO_MANY_REQUESTS, "Try-on rate limit exceeded");
        }
    }
}
