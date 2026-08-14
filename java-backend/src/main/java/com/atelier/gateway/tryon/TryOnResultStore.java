package com.atelier.gateway.tryon;

import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

public interface TryOnResultStore {
    void put(UUID jobId, byte[] image, Duration ttl);
    void extend(UUID jobId, Duration ttl);
    Optional<byte[]> get(UUID jobId);
    void delete(UUID jobId);
}
