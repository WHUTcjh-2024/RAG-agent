package com.atelier.gateway.tryon;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "tryon")
public record TryOnProperties(
    String inferenceBaseUrl,
    String internalToken,
    int workerCount,
    int queueCapacity,
    int maxAttempts,
    int rateLimitCount,
    Duration rateLimitWindow,
    Duration resultTtl,
    Duration savedResultTtl,
    Duration providerTimeout,
    Duration processingLease,
    String resultSigningSecret
) {
    public TryOnProperties {
        if (workerCount < 1 || workerCount > 64 || queueCapacity < 1 || queueCapacity > 4096
            || maxAttempts < 1 || maxAttempts > 10 || rateLimitCount < 1 || rateLimitCount > 1000) {
            throw new IllegalArgumentException("Try-on concurrency configuration is out of range");
        }
        if (resultSigningSecret == null || resultSigningSecret.isBlank()) {
            throw new IllegalArgumentException("tryon.result-signing-secret must be configured");
        }
    }
}
