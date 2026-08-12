package com.atelier.gateway.tryon;

import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisTryOnResultStore implements TryOnResultStore {
    private final RedisTemplate<String, byte[]> redisTemplate;

    public RedisTryOnResultStore(RedisTemplate<String, byte[]> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    @Override
    public void put(UUID jobId, byte[] image, Duration ttl) {
        redisTemplate.opsForValue().set(key(jobId), image, ttl);
    }

    @Override
    public void extend(UUID jobId, Duration ttl) {
        redisTemplate.expire(key(jobId), ttl);
    }

    @Override
    public Optional<byte[]> get(UUID jobId) {
        return Optional.ofNullable(redisTemplate.opsForValue().get(key(jobId)));
    }

    @Override
    public void delete(UUID jobId) {
        redisTemplate.delete(key(jobId));
    }

    private String key(UUID jobId) {
        return "fitme:tryon:result:" + jobId;
    }
}
